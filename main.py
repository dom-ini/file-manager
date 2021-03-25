import datetime as dt
import subprocess
import shutil
import sys
import os

from typing import List, Union, Any, Tuple, Optional
from distutils import dir_util
from collections import deque
from pathlib import Path

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import qrc_resources
import pyperclip
if os.name == 'nt':
    import win32api
    import win32con
    import pywintypes


class CustomTreeView(QTreeView):
    """
    Custom class for PyQt TreeView
    """
    itemDropped = pyqtSignal(QPoint, list)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        colPos = self.columnAt(e.pos().x())

        # if LMB is pressed and mouse cursor is over empty space
        if (QApplication.mouseButtons() == Qt.LeftButton and not self.indexAt(e.pos()).siblingAtColumn(0).data()) \
                or colPos == 4:
            self.setDragEnabled(False)
            self._origin = QPoint(e.pos().x(), e.pos().y() + self.header().height())
            self._rubberBand = QRubberBand(QRubberBand.Rectangle, self)
            self._rubberBand.setGeometry(QRect(self._origin, QSize()))
            self._rubberBand.show()
        editor = self.indexWidget(self.currentIndex().siblingAtColumn(0))

        # if editor of any item is opened, close it on mouse click
        if editor:
            self.commitData(editor)
            self.closeEditor(editor, QAbstractItemDelegate.SubmitModelCache)
            self.itemDelegate().closeEditor.emit(editor)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        ctrlPressed = QApplication.keyboardModifiers() == Qt.ControlModifier
        mouseOverItem = bool(self.indexAt(e.pos()).siblingAtColumn(0).data())
        originOverItem = bool(hasattr(self, '_origin') and self.indexAt(self._origin).siblingAtColumn(0).data())

        # clears selection if box selection doesn't contain any item and CTRL is not pressed
        if not ctrlPressed and ((not mouseOverItem and e.pos().y() > 0) and not originOverItem):
            self.clearSelection()

        # update box selection position
        if QApplication.mouseButtons() == Qt.LeftButton and hasattr(self, '_rubberBand'):
            pos = QPoint(e.pos().x(), max(e.pos().y() + self.header().height(), self.header().height()))
            self._rubberBand.setGeometry(QRect(self._origin, pos).normalized())
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        self.setDragEnabled(True)
        if hasattr(self, '_rubberBand'):
            self._rubberBand.hide()
        super().mouseReleaseEvent(e)

    def startDrag(self, supportedActions: Union[Qt.DropActions, Qt.DropAction]) -> None:
        if QApplication.mouseButtons() == Qt.LeftButton:
            super().startDrag(supportedActions)

    def dropEvent(self, e: QDropEvent) -> None:
        if e.mimeData().hasFormat('application/x-qstandarditemmodeldatalist'):
            e.acceptProposedAction()
            self.itemDropped.emit(e.pos(), self.selectedIndexes())


class FileManager(QMainWindow):
    """
    Custom class for PyQt MainWindow, GUI file manager
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle('File Manager')
        self.setWindowIcon(QIcon(':folder.png'))
        self.setMinimumSize(800, 600)
        self.setGeometry(0, 0, 1050, 768)

        self._SIZES_SUFFIX = {
            0: 'B',
            1: 'KB',
            2: 'MB',
            3: 'GB',
            4: 'TB', }

        # list for storing paths of files to be copied/cut
        self._fileClipboard = []

        # initial path for file manager
        self._currPath = Path.home()

        # stack for storing previously visited directories, enables the back and forward buttons functionality
        self._pathStack = deque(maxlen=20)
        self._stackIndex = -1
        self._pathStack.append(self._currPath)

        self._createLayout()
        self._initUI()
        self._connectSignals()

        self._listDirectories()

    def _createLayout(self) -> None:
        """
        Creates main window layout
        """
        # layouts
        self._mainLayout = QVBoxLayout()
        self._fileViewLayout = QHBoxLayout()
        self._sideFileLayout = QVBoxLayout()
        self._addressBarLayout = QHBoxLayout()

        # side file view
        self._documentsButton = QPushButton('Go to Documents')
        self._desktopButton = QPushButton('Go to Desktop')
        self._sideFileView = QTreeView()
        self._sideFileView.setFixedWidth(250)
        self._sideModel = QFileSystemModel()
        self._sideModel.setRootPath(str(self._currPath))
        self._sideFileView.setModel(self._sideModel)
        for i in range(1, 4):
            self._sideFileView.hideColumn(i)  # leave only directory names on the side file view
        self._sideFileView.setHeaderHidden(True)
        self._sideFileView.setFont(QFont('Consolas'))
        self._sideModel.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot)
        self._sideFileLayout.addWidget(self._documentsButton)
        self._sideFileLayout.addWidget(self._desktopButton)
        self._sideFileLayout.addWidget(self._sideFileView)
        self._fileViewLayout.addLayout(self._sideFileLayout)

        # central file view
        self._mainFileView = CustomTreeView()
        self._mainFileView.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._mainFileView.setAlternatingRowColors(True)
        self._mainFileView.setSortingEnabled(True)
        self._mainFileView.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._model = QStandardItemModel()
        self._modelHeaders = ['Filename', 'Type', 'Modified On', 'Size', '']
        self._mainFileView.setModel(self._model)
        self._mainFileView.setFont(QFont('Consolas'))
        self._mainFileView.setRootIsDecorated(False)
        self._mainFileView.setItemsExpandable(False)
        self._mainFileView.setDragEnabled(True)
        self._mainFileView.setAcceptDrops(True)
        self._mainFileView.setDropIndicatorShown(True)
        self._mainFileView.header().setFirstSectionMovable(True)
        self._mainFileView.setFocusPolicy(Qt.NoFocus)
        self._fileViewLayout.addWidget(self._mainFileView)

        # navigation buttons
        self._goBackBtn = QToolButton()
        self._goUpBtn = QToolButton()
        self._goForwardBtn = QToolButton()
        self._addressBarLayout.addWidget(self._goBackBtn)
        self._addressBarLayout.addWidget(self._goUpBtn)
        self._addressBarLayout.addWidget(self._goForwardBtn)

        # address bar
        self._addressBar = QLineEdit()
        self._addressBarLayout.addWidget(self._addressBar)
        self._mainLayout.addLayout(self._addressBarLayout)
        self._mainLayout.addLayout(self._fileViewLayout)

        # main parent widget
        self._centralWidget = QWidget()
        self._centralWidget.setLayout(self._mainLayout)
        self.setCentralWidget(self._centralWidget)

    def _initUI(self) -> None:
        """
        Builds additional main window elements and creates actions
        """
        self._createActions()
        self._addActionsToMoveButtons()
        self._createToolBar()
        self._createStatusBar()
        self._createMainContextMenu()

    def _createActions(self) -> None:
        """
        Creates action buttons
        """
        # actions for File tab
        self._openAction = QAction(QIcon(":open.png"), '&Open', self)
        self._newFileAction = QAction(QIcon(":new_file.png"), '&New File', self)
        self._newFolderAction = QAction(QIcon(":new_folder.png"), '&New Folder', self)
        self._exitAction = QAction(QIcon(":exit.png"), '&Exit', self)

        # actions for Edit tab
        self._copyFileAction = QAction(QIcon(":copy_file.png"), '&Copy', self)
        self._copyPathAction = QAction(QIcon(":copy_path.png"), '&Copy Path', self)
        self._pasteFileAction = QAction(QIcon(":paste.png"), '&Paste', self)
        self._cutAction = QAction(QIcon(":cut.png"), '&Cut', self)
        self._renameAction = QAction(QIcon(":rename.png"), '&Rename', self)
        self._bulkRenameAction = QAction(QIcon(":bulk_rename.png"), '&Bulk Rename...', self)
        self._deleteAction = QAction(QIcon(":delete.png"), '&Delete', self)

        # actions for View tab
        self._refreshAction = QAction(QIcon(':refresh.png'), '&Refresh', self)
        self._sortAction = QAction(QIcon(':sort.png'), '&Sort...', self)

        # actions for navigation buttons
        self._goUpAction = QAction(QIcon(':go_up.png'), '&Go Up', self)
        self._goBackAction = QAction(QIcon(':go_back.png'), '&Back', self)
        self._goForwardAction = QAction(QIcon(':go_forward.png'), '&Forward', self)

        self._moveActions = [self._goUpAction, self._goBackAction, self._goForwardAction]
        self._fileActions = [self._openAction, self._newFileAction, self._newFolderAction, self._exitAction]
        self._editActions = [self._copyFileAction, self._copyPathAction, self._cutAction, self._pasteFileAction,
                             self._renameAction, self._bulkRenameAction, self._deleteAction]
        self._viewActions = [self._refreshAction, self._sortAction]

        self._pasteFileAction.setEnabled(False)

        # keyboard shortcuts for actions
        self._openAction.setShortcut('Enter')
        self._newFileAction.setShortcut('Ctrl+N')
        self._newFolderAction.setShortcut('Ctrl+Shift+N')
        self._exitAction.setShortcut('Ctrl+Q')
        self._copyFileAction.setShortcut('Ctrl+C')
        self._copyPathAction.setShortcut('Ctrl+Shift+C')
        self._cutAction.setShortcut('Ctrl+X')
        self._pasteFileAction.setShortcut('Ctrl+V')
        self._renameAction.setShortcut('F2')
        self._deleteAction.setShortcut('Delete')
        self._refreshAction.setShortcut('F5')

    def _addActionsToMoveButtons(self) -> None:
        """
        Sets up actions for navigation buttons
        """
        self._goBackBtn.setDefaultAction(self._goBackAction)
        self._goUpBtn.setDefaultAction(self._goUpAction)
        self._goForwardBtn.setDefaultAction(self._goForwardAction)

    def _createToolBar(self) -> None:
        """
        Creates tabbed toolbar (pseudo-ribbon)
        """
        toolsToolBar = QToolBar()
        self.addToolBar(Qt.TopToolBarArea, toolsToolBar)
        toolsToolBar.setMovable(False)
        iconSize = QSize(50, 50)

        tabs = QTabWidget()

        fileTab = QToolBar()
        fileTab.setIconSize(iconSize)
        fileTab.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        for action in self._fileActions:
            fileTab.addAction(action)

        editTab = QToolBar()
        editTab.setIconSize(iconSize)
        editTab.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        for action in self._editActions:
            editTab.addAction(action)

        viewTab = QToolBar()
        viewTab.setIconSize(iconSize)
        viewTab.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        for action in self._viewActions:
            viewTab.addAction(action)

        # widget for filtering files and directories in the current path
        filterLayout = QHBoxLayout()
        filterLayout.setAlignment(Qt.AlignLeft)
        filterWidget = QWidget()
        filterLabel = QLabel('Filter:')
        filterLabel.setFixedWidth(filterLabel.fontMetrics().boundingRect(filterLabel.text()).width())
        self._filterField = QLineEdit()
        self._filterField.setFixedWidth(200)
        filterLayout.addWidget(filterLabel)
        filterLayout.addWidget(self._filterField)
        filterWidget.setLayout(filterLayout)
        viewTab.addSeparator()
        viewTab.addWidget(filterWidget)

        tabs.addTab(fileTab, 'File')
        tabs.addTab(editTab, 'Edit')
        tabs.addTab(viewTab, 'View')
        toolsToolBar.addWidget(tabs)

    def _createStatusBar(self) -> None:
        """
        Sets up the status bar
        """
        self._statusBar = QStatusBar()
        self.setStatusBar(self._statusBar)

    def _createMainContextMenu(self) -> None:
        """
        Creates right-click menu for main file view
        """
        # separators for improved readability
        separator1 = QAction(self)
        separator1.setSeparator(True)
        separator2 = QAction(self)
        separator2.setSeparator(True)

        self._mainFileView.setContextMenuPolicy(Qt.ActionsContextMenu)
        for action in self._fileActions:
            if action == self._exitAction:  # don't include Exit button in the context menu
                continue
            self._mainFileView.addAction(action)
        self._mainFileView.addAction(separator1)
        for action in self._editActions:
            self._mainFileView.addAction(action)
        self._mainFileView.addAction(separator2)
        for action in self._viewActions:
            self._mainFileView.addAction(action)

    def _connectSignals(self) -> None:
        """
        Connects buttons and actions with functions
        """
        self._documentsButton.pressed.connect(lambda: self._openPath(path=Path.home().joinpath('Documents')))
        self._desktopButton.pressed.connect(lambda: self._openPath(path=Path.home().joinpath('Desktop')))

        # File tab actions
        self._openAction.triggered.connect(lambda: self._openPath(self._mainFileView.selectedIndexes()))
        self._newFolderAction.triggered.connect(lambda: self._addRowToModel(True))
        self._newFileAction.triggered.connect(lambda: self._addRowToModel(False))
        self._exitAction.triggered.connect(self.close)

        # Edit tab actions
        self._copyFileAction.triggered.connect(lambda: self._copyFile(self._mainFileView.selectedIndexes()))
        self._copyPathAction.triggered.connect(lambda: self._copyPath(self._mainFileView.selectedIndexes()))
        self._cutAction.triggered.connect(lambda: self._copyFile(self._mainFileView.selectedIndexes(), cut=True))
        self._pasteFileAction.triggered.connect(self._pasteFile)
        self._renameAction.triggered.connect(lambda: self._renameTrigger(self._mainFileView.selectedIndexes()))
        self._bulkRenameAction.triggered.connect(lambda: self._bulkRename(self._mainFileView.selectedIndexes()))
        self._deleteAction.triggered.connect(lambda: self._deleteItem(self._mainFileView.selectedIndexes()))

        # View tab actions
        self._refreshAction.triggered.connect(self._listDirectories)
        self._sortAction.triggered.connect(self._sortHandler)

        # Navigation buttons' actions
        self._goBackAction.triggered.connect(self._goBack)
        self._goForwardAction.triggered.connect(self._goForward)
        self._goUpAction.triggered.connect(self._goUp)

        # path opening from main file view, side file view and address bar
        self._mainFileView.doubleClicked.connect(lambda: self._openPath(self._mainFileView.selectedIndexes()))
        self._sideFileView.clicked.connect(lambda: self._openPath(self._sideFileView.selectedIndexes(), False))
        self._addressBar.returnPressed.connect(lambda: self._openPath(path=Path(self._addressBar.text())))

        # auto-adjustment of side file view width
        self._sideFileView.expanded.connect(lambda: self._sideFileView.resizeColumnToContents(0))

        # handling item edit
        self._mainFileView.itemDelegate().closeEditor.connect(self._editHandler)

        # drag and drop functionality
        self._mainFileView.itemDropped.connect(self._dropMove)

        # View tab filter
        self._filterField.textChanged.connect(self._listDirectories)
        self._filterField.returnPressed.connect(lambda: self._listDirectories(self._filterField.text()))

    def _listDirectories(self, filter: str = None) -> None:
        """
        Shows all files in the current directory

        :param filter: show only files containing that text
        """
        self._addressBar.setText(str(self._currPath))
        self._resetMainFileView()
        fileIco = QIcon(':file_sm')
        folderIco = QIcon(':folder_sm')
        fileCutIco = QIcon(':file_sm_cut')
        folderCutIco = QIcon(':folder_sm_cut')
        for file in self._currPath.glob('*'):
            if self._isPathHidden(file):
                continue
            if filter and filter.lower() not in file.name.lower():
                continue
            if file.is_dir():
                size = QStandardItem('')
                type = QStandardItem('Folder')
                icon = folderIco if Path(file) not in self._fileClipboard else folderCutIco
            else:
                size = QStandardItem(self._prettifySize(file.stat().st_size))
                type = QStandardItem(f'{file.suffix.upper()}{" " if file.suffix else ""}File')
                icon = fileIco if Path(file) not in self._fileClipboard else fileCutIco
            item = QStandardItem(icon, file.name)
            mod_date_str = dt.datetime.fromtimestamp(file.stat().st_mtime).strftime('%d.%m.%Y %H:%M')
            mod_date = QStandardItem(mod_date_str)
            self._model.appendRow([item, type, mod_date, size])
        self._mainFileView.sortByColumn(1, Qt.DescendingOrder)

    def _resetMainFileView(self) -> None:
        """
        Clears the main file view
        """
        self._model.clear()
        self._model.setHorizontalHeaderLabels(self._modelHeaders)
        self._mainFileView.setColumnWidth(0, 250)
        self._mainFileView.setColumnWidth(2, 150)
        self._mainFileView.resizeColumnToContents(4)

    def _prettifySize(self, size) -> str:
        """
        Converts filesize in bytes to the smallest possible number

        :param size: filesize in bytes
        :return: filesize with proper suffix
        """
        iteration = 0
        while size >= 1024:
            size /= 1024
            iteration += 1
        size = f'{size:.2f}'.rstrip('0').rstrip('.').rjust(6)  # 6 is maximal number of digits of any input
        return f'{size} {self._SIZES_SUFFIX[iteration]}'

    def _isPathHidden(self, path: Path) -> bool:
        """
        Determines if the given path is hidden or not

        :param path: path to check
        :return: True if the given path is hidden, False otherwise
        """
        if os.name == 'nt':  # on Windows, check Windows flags of the path
            try:
                fileAttrs = win32api.GetFileAttributes(str(path))
                return fileAttrs & (win32con.FILE_ATTRIBUTE_HIDDEN | win32con.FILE_ATTRIBUTE_SYSTEM)
            except pywintypes.error:
                return False
        else:
            return path.name.startswith('.')

    def _openPath(self, item: List[QModelIndex] = None, mainView: bool = True, path: Path = None,
                  ignoreStack: bool = False) -> None:
        """
        Opens the given path in main file view

        :param item: list of selected items
        :param mainView: if the item was selected in the main file view
        :param path: path to be opened
        :param ignoreStack: if the opening action should not be listed in last visited directories stack
        """
        if not item and not path:
            return
        if mainView and item:
            dir_name = self._model.data(item[0])  # if multiple items are selected, open the first one
            path = self._currPath.parent if dir_name == '..' else self._currPath.joinpath(dir_name)
        elif not mainView and item:
            path = Path(self._sideModel.filePath(item[0]))

        if path.is_dir():
            try:
                os.listdir(str(path))  # used, because Path.glob() doesn't throw PermissionError
                if not ignoreStack and not path == self._currPath:
                    for _ in range(-1, self._stackIndex, -1):
                        self._pathStack.pop()
                    self._pathStack.append(path)
                    self._stackIndex = -1
                self._currPath = path
                self._listDirectories()
            except PermissionError:
                self._statusBar.showMessage('Access denied!', 3000)
        elif path.is_file():
            subprocess.Popen(str(path), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).poll()
        else:
            self._statusBar.showMessage('Invalid path!', 3000)
            self._listDirectories()

    def _addRowToModel(self, isDir: bool) -> None:
        """
        Add item to main file view before creating the new file/folder

        :param isDir: if it's a folder to be created
        """
        if isDir:
            self._model.appendRow(QStandardItem(QIcon(':folder_sm'), 'New Folder'))
            self._editItemType = 'folder'
        else:
            self._model.appendRow(QStandardItem(QIcon(':file_sm'), 'New File'))
            self._editItemType = 'file'
        self._mainFileView.scrollToBottom()
        self._editItem = self._model.item(self._model.rowCount() - 1)
        self._editItemNameBefore = self._editItem.text()
        index = self._model.indexFromItem(self._editItem)
        self._mainFileView.setCurrentIndex(index)
        self._mainFileView.edit(index)

    def _editHandler(self) -> None:
        """
        Handler for closeEditor signal
        """
        if self._editItemType:
            self._createDir()
        else:
            self._renameDir()

    def _createDir(self) -> None:
        """
        Creates a folder/file based on current directory and name given to the item editor
        """
        try:
            name = self._editItem.text()
            path = self._currPath.joinpath(name)
            if self._editItemType == 'folder':
                path.mkdir()
            elif self._editItemType == 'file':
                if len(self._model.findItems(name)) > 1:
                    # this method of creating file does not prevent duplicates, so exception is raised manually
                    raise FileExistsError
                with path.open('w+', encoding='utf-8'):
                    pass
            self._listDirectories()
            createdItem = self._model.findItems(name)
            index = self._model.indexFromItem(createdItem[0])
            self._mainFileView.scrollTo(index)
            self._mainFileView.setCurrentIndex(index)
        except FileExistsError:
            self._statusBar.showMessage('File/folder with that name already exists!', 3000)
            self._listDirectories()
        except PermissionError:
            self._statusBar.showMessage('File/folder with that name could not be created!', 3000)
            self._listDirectories()

    def _copyFile(self, items: List[QModelIndex], cut: bool = False) -> None:
        """
        Copies the paths to given files and stores them in the internal clipboard

        :param items: list of selected items
        :param cut: if the files have to be moved instead of copied
        """
        if len(items) == 0:
            return
        items = [x for i, x in enumerate(items) if i % len(self._modelHeaders) == 0]
        self._fileClipboard = [self._currPath.joinpath(self._model.itemFromIndex(x).text()) for x in items]
        self._fileClipboard.append(cut)
        self._listDirectories()
        self._pasteFileAction.setEnabled(True)
        self._statusBar.showMessage('File copied to clipboard!', 3000)

    def _copyPath(self, items: List[QModelIndex]) -> None:
        """
        Copies the paths to given dirs and stores them in the external clipboard

        :param items: list of selected items
        """
        if len(items) == 0:
            return
        items = [x for i, x in enumerate(items) if i % len(self._modelHeaders) == 0]
        items = [str(self._currPath.joinpath(self._model.itemFromIndex(x).text())) for x in items]
        pyperclip.copy(', '.join(items))
        self._statusBar.showMessage('Path copied to clipboard!', 3000)

    def _pasteFile(self) -> None:
        """
        Pastes the dirs (based on paths in internal clipboard) to the current directory
        """
        if not self._fileClipboard:
            return
        cut = self._fileClipboard.pop()
        filenames = [x.name for x in self._fileClipboard]
        destPaths = [self._currPath.joinpath(x) for x in filenames]
        try:
            duplicates = []
            for src, dest in zip(self._fileClipboard, destPaths):
                if src == dest:
                    raise shutil.SameFileError
                if dest in self._currPath.glob('*'):
                    duplicates.append(dest)
            if duplicates:
                if self._overwriteFileMsgBox(duplicates) == QMessageBox.Cancel:
                    self._fileClipboard.clear()
                    self._pasteFileAction.setEnabled(False)
                    return
            for src, dest in zip(self._fileClipboard, destPaths):
                if cut and src.is_file():
                    shutil.move(str(src), str(dest))
                elif src.is_dir():
                    dir_util.copy_tree(str(src), str(dest))
                    if cut:
                        shutil.rmtree(src)
                elif src.is_file():
                    shutil.copy(str(src), str(dest))
                elif not src.exists():
                    raise FileNotFoundError
            self._statusBar.showMessage('File pasted!', 3000)
            self._fileClipboard.clear()
            self._pasteFileAction.setEnabled(False)
        except shutil.SameFileError:
            self._statusBar.showMessage('You cannot overwrite the same file!', 3000)
            self._fileClipboard.clear()
        except PermissionError:
            self._statusBar.showMessage('No permission to copy the file!', 3000)
            self._fileClipboard.clear()
        except FileNotFoundError:
            self._statusBar.showMessage('Cannot find the source file!', 3000)
            self._fileClipboard.clear()
        finally:
            self._listDirectories()

    def _overwriteFileMsgBox(self, duplicates: List[Path]) -> int:
        """
        MessageBox to confirm file overwriting

        :param duplicates: list of duplicate files/folders
        :return: 1 if Ok button clicked, 0 otherwise
        """
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Warning)
        if len(duplicates) > 1:
            msgText = f"Do you want to overwrite {len(duplicates)} files?"
        else:
            msgText = f"Do you want to overwrite '{duplicates[0].name}'?"
        msgBox.setText(msgText)
        msgBox.setWindowTitle("Confirm overwrite")
        msgBox.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)

        return msgBox.exec()

    def _renameTrigger(self, item: List[QModelIndex]) -> None:
        """
        Renames the given folder/file

        :param item: the item from main file view representing the folder/file to be renamed
        """
        if not item:
            return
        item = item[0].siblingAtColumn(0)
        self._editItemNameBefore = item.data()
        self._editItem = self._model.itemFromIndex(item)
        self._editItemType = None
        self._mainFileView.edit(item)

    def _renameDir(self) -> None:
        """
        Renames selected folder/file to the name given in the item editor
        """
        try:
            path = self._currPath.joinpath(self._editItemNameBefore)
            nameAfter = self._editItem.text()
            pathTo = self._currPath.joinpath(nameAfter)
            path.rename(pathTo)
            self._listDirectories()
            renamedItem = self._model.findItems(nameAfter)
            index = self._model.indexFromItem(renamedItem[0])
            self._mainFileView.scrollTo(index)
            self._mainFileView.setCurrentIndex(index)
        except FileExistsError:
            self._statusBar.showMessage('File/folder with that name already exists!', 3000)
            self._listDirectories()

    def _bulkRename(self, items: List[QModelIndex]) -> None:
        """
        Renames multiple files based on user-inputted parameters

        :param items: list of selected items
        """
        items = [self._currPath.joinpath(x.siblingAtColumn(0).data())
                 for i, x in enumerate(items) if i % len(self._modelHeaders) == 0]
        items = list(filter(lambda x: x.is_file(), items))
        illegalChars = {'<', '>', ':', '"', '/', '\\', '|', '?', '*'}
        while True:
            response, onlySelected, extension, prefix, startNumber = self._bulkRenameDialog()
            if not response:
                break
            if not items and onlySelected:
                self._bulkRenameMsgBox('No files were selected!')
                continue
            elif any((c in illegalChars) for c in prefix):
                self._bulkRenameMsgBox('Illegal characters in prefix!')
                continue
            fileFound = False
            for path in self._currPath.glob('*'):
                try:
                    if extension is not None and extension != path.suffix.lstrip('.'):
                        continue
                    if path.is_file() and (not onlySelected or path in items):
                        path.rename(self._currPath.joinpath(f'{prefix}{str(startNumber)}{path.suffix}'))
                        startNumber += 1
                        fileFound = True
                except FileExistsError:
                    self._bulkRenameMsgBox(f'File {path.name} already exists!')
                    self._statusBar.showMessage('Operation aborted!', 3000)
                    return
                finally:
                    self._listDirectories()
            if not fileFound:
                self._bulkRenameMsgBox('No suitable files in given directory!')
                continue
            break

    def _bulkRenameDialog(self) -> Tuple[Any, Any, Optional[Any], Any, Union[int, Any]]:
        """
        Dialog for setting parameters for bulk rename

        :return: tuple of parameters
        """
        dialog = QDialog()
        dialog.setWindowTitle('Bulk Rename')
        dialog.setWindowIcon(QIcon(':bulk_rename.png'))

        # layouts
        dialogLayout = QVBoxLayout()
        extensionLayout = QHBoxLayout()
        prefixLayout = QHBoxLayout()
        startNumLayout = QHBoxLayout()
        namePreviewLayout = QHBoxLayout()
        buttonBoxLayout = QHBoxLayout()

        # path bar
        dialogLayout.addWidget(QLabel('Rename files in:'))
        pathLine = QLineEdit(str(self._currPath))
        pathLine.setReadOnly(True)
        dialogLayout.addWidget(pathLine)

        # checkbox for renaming only selected
        onlySelectedCheck = QCheckBox('Rename only selected files')
        dialogLayout.addWidget(onlySelectedCheck)

        # checkbox and text input for extension of files to be renamed
        extensionCheck = QCheckBox('Rename only files with extension:')
        extensionLine = QLineEdit()
        extensionLine.setEnabled(False)
        extensionLine.setPlaceholderText('Without dot, e.g. jpg')
        extensionLayout.addWidget(extensionCheck)
        extensionLayout.addWidget(extensionLine)
        dialogLayout.addLayout(extensionLayout)
        # disable text input if checkbox is not ticked
        extensionCheck.stateChanged.connect(lambda: extensionLine.setEnabled(not extensionLine.isEnabled()))

        # text input for filename pattern
        prefixLabel = QLabel('Prefix:')
        prefixLine = QLineEdit()
        prefixLabel.setFixedWidth(40)
        prefixLine.setFixedWidth(100)
        prefixLayout.addWidget(prefixLabel)
        prefixLayout.addWidget(prefixLine)
        prefixLayout.setAlignment(Qt.AlignLeft)
        dialogLayout.addLayout(prefixLayout)

        # checkbox and spinbox for filenames' starting index
        startNumCheck = QCheckBox('Start from number:')
        startNumSpin = QSpinBox()
        startNumSpin.setEnabled(False)
        startNumLayout.setAlignment(Qt.AlignLeft)
        startNumSpin.setFixedWidth(75)
        startNumSpin.setMinimum(0)
        startNumSpin.setMaximum(1_000_000)
        startNumSpin.setAccelerated(True)
        startNumLayout.addWidget(startNumCheck)
        startNumLayout.addWidget(startNumSpin)
        dialogLayout.addLayout(startNumLayout)
        # disable spinbox if checkbox is not ticked
        startNumCheck.stateChanged.connect(lambda: startNumSpin.setEnabled(not startNumSpin.isEnabled()))

        # read-only text field with the preview of name of the first file
        namePreviewLabel = QLabel('Filename preview:')
        namePreviewLine = QLineEdit()
        namePreviewLine.setReadOnly(True)
        namePreviewPush = QPushButton('Preview')
        namePreviewLayout.addWidget(namePreviewLabel)
        namePreviewLayout.addWidget(namePreviewLine)
        namePreviewLayout.addWidget(namePreviewPush)
        dialogLayout.addLayout(namePreviewLayout)
        namePreviewPush.clicked.connect(
            lambda: namePreviewLine.setText(f"{prefixLine.text()}"
                                            f"{str(startNumSpin.value()) if startNumCheck.isChecked() else '0'}"))

        # Ok and Cancel buttons
        buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(dialog.accept)
        buttonBox.rejected.connect(dialog.reject)
        buttonBoxLayout.addStretch()
        buttonBoxLayout.addWidget(buttonBox)
        buttonBoxLayout.addStretch()
        dialogLayout.addLayout(buttonBoxLayout)

        dialog.setLayout(dialogLayout)

        dialogResponse = dialog.exec()
        extension = extensionLine.text() if extensionCheck.isChecked() else None
        startNum = startNumSpin.value() if startNumCheck.isChecked() else 0

        return dialogResponse, onlySelectedCheck.isChecked(), extension, prefixLine.text(), startNum

    def _bulkRenameMsgBox(self, msgText: str) -> int:
        """
        MessageBox for errors in bulk rename

        :param msgText: text to be displayed in the MessageBox
        :return: 1 if Ok button clicked, 0 otherwise
        """
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Warning)
        msgBox.setWindowIcon(QIcon(':bulk_rename.png'))
        msgBox.setText(msgText)
        msgBox.setWindowTitle("Bulk Rename")
        msgBox.setStandardButtons(QMessageBox.Ok)

        return msgBox.exec()

    def _deleteItem(self, items: List[QModelIndex]) -> None:
        """
        Deletes selected files/folders

        :param items: list of selected items
        """
        if not items:
            return
        files = [x for i, x in enumerate(items) if i % len(self._modelHeaders) == 0]

        if self._deleteItemMsgBox(files) == QMessageBox.Ok:
            for file in files:
                path = self._currPath.joinpath(file.data())
                try:
                    if path.is_dir():
                        shutil.rmtree(path)
                    elif path.is_file():
                        os.remove(path)
                except FileNotFoundError:
                    self._statusBar.showMessage('Something went wrong!', 3000)
            self._listDirectories()

    def _deleteItemMsgBox(self, files: List[QModelIndex]) -> int:
        """
        MessageBox for confirmation of deleting items

        :param files: list of files to be deleted
        :return: 1 if Ok button clicked, 0 otherwise
        """
        msgBox = QMessageBox()
        msgBox.setWindowTitle("Confirm delete")
        msgBox.setIcon(QMessageBox.Warning)
        filename = files[0].data() if len(files) == 1 else None
        msgText = f"Are you sure to delete '{filename}'?" if filename else f"Are you sure to delete {len(files)} items?"
        msgBox.setText(msgText)
        msgBox.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)

        return msgBox.exec()

    def _sortHandler(self) -> None:
        """
        Handler for the sort action
        """
        response, columnIndex, ascending = self._sortDialog()
        order = Qt.AscendingOrder if ascending else Qt.DescendingOrder
        if response:
            self._mainFileView.sortByColumn(columnIndex, order)

    def _sortDialog(self) -> Tuple[Any, Any, Any]:
        """
        Dialog for setting parameters for sorting

        :return: tuple of sort parameters
        """
        dialog = QDialog()
        dialog.setFixedSize(300, 150)
        dialog.setWindowTitle('Sort')
        dialog.setWindowIcon(QIcon(':sort.png'))

        # layouts
        dialogLayout = QVBoxLayout()
        formLayout = QFormLayout()
        orderRadioLayout = QVBoxLayout()
        buttonBoxLayout = QHBoxLayout()

        # sort by column combobox
        sortLabel = QLabel('Sort by:')
        sortComboBox = QComboBox()
        sortComboBox.addItems(self._modelHeaders)

        # order choosing radio buttons
        orderLabel = QLabel('Order:')
        orderRadioAsc = QRadioButton('ascending')
        orderRadioAsc.setChecked(True)
        orderRadioDesc = QRadioButton('descending')
        orderRadioLayout.addWidget(orderRadioAsc)
        orderRadioLayout.addWidget(orderRadioDesc)

        formLayout.addRow(sortLabel, sortComboBox)
        formLayout.addRow(orderLabel, orderRadioLayout)

        # Ok and Cancel buttons
        buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(dialog.accept)
        buttonBox.rejected.connect(dialog.reject)
        buttonBoxLayout.addStretch()
        buttonBoxLayout.addWidget(buttonBox)
        buttonBoxLayout.addStretch()

        dialogLayout.addLayout(formLayout)
        dialogLayout.addLayout(buttonBoxLayout)
        dialogLayout.setAlignment(Qt.AlignCenter)

        dialog.setLayout(dialogLayout)

        dialogResponse = dialog.exec()

        return dialogResponse, sortComboBox.currentIndex(), orderRadioAsc.isChecked()

    def _dropMove(self, point: QPoint, selectedFiles: List[QModelIndex]) -> None:
        """
        Handles drag and drop file moving

        :param point: point where the dragged items are dropped
        :param selectedFiles: list of selected items
        """
        selectedFiles = [self._currPath.joinpath(x.data()) for i, x in enumerate(selectedFiles)
                         if i % len(self._modelHeaders) == 0]
        try:
            filename = self._mainFileView.indexAt(point).siblingAtColumn(0).data()
            dest = self._currPath.joinpath(filename)
            if dest.is_file():
                return
            duplicates = []
            for src in selectedFiles:
                dest = self._currPath.joinpath(filename).joinpath(src.name)
                if str(src) in str(dest):
                    return
                if dest.exists():
                    duplicates.append(dest)
            if duplicates:
                if self._overwriteFileMsgBox(duplicates) == QMessageBox.Cancel:
                    return
            for src in selectedFiles:
                dest = self._currPath.joinpath(filename).joinpath(src.name)
                if not src.exists():
                    raise FileNotFoundError
                if src.is_file():
                    shutil.move(str(src), str(dest))
                elif src.is_dir():
                    dir_util.copy_tree(str(src), str(dest))
                    shutil.rmtree(src)
        except FileNotFoundError:
            self._statusBar.showMessage('File not found!', 3000)
        except TypeError:  # when the files are dropped on empty area
            pass
        finally:
            self._listDirectories()

    def _goBack(self) -> None:
        """
        Returns to the last visited directory (goes back in directories stack)
        """
        if abs(self._stackIndex) < len(self._pathStack):
            self._stackIndex -= 1
            self._openPath(path=self._pathStack[self._stackIndex], ignoreStack=True)

    def _goForward(self) -> None:
        """
        Goes forward in directories stack
        """
        if self._stackIndex < -1:
            self._stackIndex += 1
            self._openPath(path=self._pathStack[self._stackIndex], ignoreStack=True)

    def _goUp(self) -> None:
        """
        Goes one directory up
        """
        self._openPath(path=self._currPath.parent)


def main():
    app = QApplication(sys.argv)
    window = FileManager()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
