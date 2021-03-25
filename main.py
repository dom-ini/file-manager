import datetime as dt
import subprocess
import shutil
import sys
import os

from typing import List, Union
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


class CustTreeView(QTreeView):
    itemDropped = pyqtSignal(QPoint, list)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        colPos = self.columnAt(e.pos().x())
        if (QApplication.mouseButtons() == Qt.LeftButton and not self.indexAt(e.pos()).siblingAtColumn(0).data()) \
                or colPos == 4:
            self.setDragEnabled(False)
            self.origin = QPoint(e.pos().x(), e.pos().y() + self.header().height())
            self.rubberBand = QRubberBand(QRubberBand.Rectangle, self)
            self.rubberBand.setGeometry(QRect(self.origin, QSize()))
            self.rubberBand.show()
        editor = self.indexWidget(self.currentIndex().siblingAtColumn(0))
        if editor:
            self.commitData(editor)
            self.closeEditor(editor, QAbstractItemDelegate.SubmitModelCache)
            self.itemDelegate().closeEditor.emit(editor)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if hasattr(self, 'origin') and not QApplication.keyboardModifiers() == Qt.ControlModifier and (
                (not self.indexAt(e.pos()).siblingAtColumn(0).data() and e.pos().y() > 0)
                and not self.indexAt(self.origin).siblingAtColumn(0).data()):
            self.clearSelection()
        if QApplication.mouseButtons() == Qt.LeftButton and hasattr(self, 'rubberBand'):
            pos = QPoint(e.pos().x(), max(e.pos().y() + self.header().height(), self.header().height()))
            self.rubberBand.setGeometry(QRect(self.origin, pos).normalized())
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        self.setDragEnabled(True)
        if hasattr(self, 'rubberBand'):
            self.rubberBand.hide()
        super().mouseReleaseEvent(e)

    def startDrag(self, supportedActions: Union[Qt.DropActions, Qt.DropAction]) -> None:
        if QApplication.mouseButtons() == Qt.LeftButton:
            super().startDrag(supportedActions)

    def dropEvent(self, e: QDropEvent) -> None:
        if e.mimeData().hasFormat('application/x-qstandarditemmodeldatalist'):
            e.acceptProposedAction()
            self.itemDropped.emit(e.pos(), self.selectedIndexes())


class FileManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('File Manager')
        self.setWindowIcon(QIcon(':folder.png'))
        self.setMinimumSize(800, 600)
        self.setGeometry(0, 0, 1050, 768)

        self.SIZES_SUFF = {
            0: 'B',
            1: 'KB',
            2: 'MB',
            3: 'GB',
            4: 'TB',
        }

        self.fileClipboard = []

        self.currPath = Path.home()

        self.pathStack = deque(maxlen=20)
        self.stackIndex = -1
        self.pathStack.append(self.currPath)

        self.mainLayout = QVBoxLayout()
        self.secLayout = QHBoxLayout()

        self.sideLayout = QVBoxLayout()
        self.documentsButton = QPushButton('Go to Documents')
        self.desktopButton = QPushButton()
        self.desktopButton = QPushButton('Go to Desktop')
        self.sideFileView = QTreeView()
        self.sideFileView.setFixedWidth(250)
        self.sideModel = QFileSystemModel()
        self.sideModel.setRootPath(str(self.currPath))
        self.sideFileView.setModel(self.sideModel)
        for i in range(1, 4):
            self.sideFileView.hideColumn(i)
        self.sideFileView.setHeaderHidden(True)
        self.sideFileView.setFont(QFont('Consolas'))
        self.sideModel.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot)
        self.sideLayout.addWidget(self.documentsButton)
        self.sideLayout.addWidget(self.desktopButton)
        self.sideLayout.addWidget(self.sideFileView)
        self.secLayout.addLayout(self.sideLayout)

        self.mainFileView = CustTreeView()
        self.mainFileView.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.mainFileView.setAlternatingRowColors(True)
        self.mainFileView.setSortingEnabled(True)
        self.mainFileView.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.model = QStandardItemModel()
        self.modelHeaders = ['Filename', 'Type', 'Modified On', 'Size', '']
        self.mainFileView.setModel(self.model)
        self.mainFileView.setFont(QFont('Consolas'))
        self.mainFileView.setRootIsDecorated(False)
        self.mainFileView.setItemsExpandable(False)
        self.mainFileView.setDragEnabled(True)
        self.mainFileView.setAcceptDrops(True)
        self.mainFileView.setDropIndicatorShown(True)
        self.mainFileView.header().setFirstSectionMovable(True)
        self.mainFileView.setFocusPolicy(Qt.NoFocus)
        self.secLayout.addWidget(self.mainFileView)

        self.addressBarLayout = QHBoxLayout()
        self.goBackBtn = QToolButton()
        self.goUpBtn = QToolButton()
        self.goForwardBtn = QToolButton()
        self.addressBarLayout.addWidget(self.goBackBtn)
        self.addressBarLayout.addWidget(self.goUpBtn)
        self.addressBarLayout.addWidget(self.goForwardBtn)
        self.addressBar = QLineEdit()
        self.addressBarLayout.addWidget(self.addressBar)
        self.mainLayout.addLayout(self.addressBarLayout)
        self.mainLayout.addLayout(self.secLayout)

        self.centralWidget = QWidget()
        self.centralWidget.setLayout(self.mainLayout)
        self.setCentralWidget(self.centralWidget)
        self.initUI()
        self.connectSignals()

        self.listDirectories()

    def initUI(self):
        self.createActions()
        self.addActionsToMoveButtons()
        self.createToolBar()
        self.createStatusBar()
        self.createMainContextMenu()

    def addActionsToMoveButtons(self):
        self.goBackBtn.setDefaultAction(self.goBackAction)
        self.goUpBtn.setDefaultAction(self.goUpAction)
        self.goForwardBtn.setDefaultAction(self.goForwardAction)

    def updateMainFileView(self):
        self.model.setHorizontalHeaderLabels(self.modelHeaders)
        self.mainFileView.setColumnWidth(0, 250)
        self.mainFileView.setColumnWidth(2, 150)
        self.mainFileView.resizeColumnToContents(4)

    def createToolBar(self):
        toolsToolBar = QToolBar()
        self.addToolBar(Qt.TopToolBarArea, toolsToolBar)
        toolsToolBar.setMovable(False)
        iconSize = QSize(50, 50)

        tabs = QTabWidget()
        fileTab = QToolBar()
        fileTab.setIconSize(iconSize)
        fileTab.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        editTab = QToolBar()
        editTab.setIconSize(iconSize)
        editTab.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        viewTab = QToolBar()
        viewTab.setIconSize(iconSize)
        viewTab.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)

        for action in self.fileActions:
            fileTab.addAction(action)
        for action in self.editActions:
            editTab.addAction(action)
        for action in self.viewActions:
            viewTab.addAction(action)

        filterWidget = QWidget()
        filterLabel = QLabel('Filter:')
        filterLabel.setFixedWidth(filterLabel.fontMetrics().boundingRect(filterLabel.text()).width())
        filterLayout = QHBoxLayout()
        filterLayout.setAlignment(Qt.AlignLeft)
        self.filterField = QLineEdit()
        self.filterField.setFixedWidth(200)
        filterLayout.addWidget(filterLabel)
        filterLayout.addWidget(self.filterField)
        filterWidget.setLayout(filterLayout)
        viewTab.addSeparator()
        viewTab.addWidget(filterWidget)

        tabs.addTab(fileTab, 'File')
        tabs.addTab(editTab, 'Edit')
        tabs.addTab(viewTab, 'View')
        toolsToolBar.addWidget(tabs)

    def createActions(self):
        self.openAction = QAction(QIcon(":open.png"), '&Open', self)
        self.newFileAction = QAction(QIcon(":new_file.png"), '&New File', self)
        self.newFolderAction = QAction(QIcon(":new_folder.png"), '&New Folder', self)
        self.exitAction = QAction(QIcon(":exit.png"), '&Exit', self)

        self.copyFileAction = QAction(QIcon(":copy_file.png"), '&Copy', self)
        self.copyPathAction = QAction(QIcon(":copy_path.png"), '&Copy Path', self)
        self.pasteFileAction = QAction(QIcon(":paste.png"), '&Paste', self)
        self.cutAction = QAction(QIcon(":cut.png"), '&Cut', self)
        self.renameAction = QAction(QIcon(":rename.png"), '&Rename', self)
        self.bulkRenameAction = QAction(QIcon(":bulk_rename.png"), '&Bulk Rename...', self)
        self.deleteAction = QAction(QIcon(":delete.png"), '&Delete', self)

        self.refreshAction = QAction(QIcon(':refresh.png'), '&Refresh', self)
        self.sortAction = QAction(QIcon(':sort.png'), '&Sort...', self)

        self.goUpAction = QAction(QIcon(':go_up.png'), '&Go Up', self)
        self.goBackAction = QAction(QIcon(':go_back.png'), '&Back', self)
        self.goForwardAction = QAction(QIcon(':go_forward.png'), '&Forward', self)

        self.moveActions = [self.goUpAction, self.goBackAction, self.goForwardAction]
        self.fileActions = [self.openAction, self.newFileAction, self.newFolderAction, self.exitAction]
        self.editActions = [self.copyFileAction, self.copyPathAction, self.pasteFileAction, self.cutAction,
                            self.renameAction, self.bulkRenameAction, self.deleteAction]
        self.viewActions = [self.refreshAction, self.sortAction]

        self.pasteFileAction.setEnabled(False)

        self.openAction.setShortcut('Enter')
        self.newFileAction.setShortcut('Ctrl+N')
        self.newFolderAction.setShortcut('Ctrl+Shift+N')
        self.exitAction.setShortcut('Ctrl+Q')
        self.copyFileAction.setShortcut('Ctrl+C')
        self.copyPathAction.setShortcut('Ctrl+Shift+C')
        self.cutAction.setShortcut('Ctrl+X')
        self.pasteFileAction.setShortcut('Ctrl+V')
        self.renameAction.setShortcut('F2')
        self.deleteAction.setShortcut('Delete')
        self.refreshAction.setShortcut('F5')

    def createStatusBar(self):
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)

    def createMainContextMenu(self):
        separator1 = QAction(self)
        separator1.setSeparator(True)
        separator2 = QAction(self)
        separator2.setSeparator(True)
        self.mainFileView.setContextMenuPolicy(Qt.ActionsContextMenu)
        for action in self.fileActions:
            if action == self.exitAction:
                continue
            self.mainFileView.addAction(action)
        self.mainFileView.addAction(separator1)
        for action in self.editActions:
            self.mainFileView.addAction(action)
        self.mainFileView.addAction(separator2)
        for action in self.viewActions:
            self.mainFileView.addAction(action)

    def connectSignals(self):
        self.documentsButton.pressed.connect(lambda: self.openPath(path=Path.home().joinpath('Documents')))
        self.desktopButton.pressed.connect(lambda: self.openPath(path=Path.home().joinpath('Desktop')))

        self.openAction.triggered.connect(lambda: self.openPath(self.mainFileView.selectedIndexes()))
        self.newFolderAction.triggered.connect(lambda: self.addRowToModel(True))
        self.newFileAction.triggered.connect(lambda: self.addRowToModel(False))
        self.exitAction.triggered.connect(self.close)

        self.copyPathAction.triggered.connect(lambda: self.copyPath(self.mainFileView.selectedIndexes()))
        self.copyFileAction.triggered.connect(lambda: self.copyFile(self.mainFileView.selectedIndexes()))
        self.pasteFileAction.triggered.connect(self.pasteFile)
        self.renameAction.triggered.connect(lambda: self.renameTrigger(self.mainFileView.selectedIndexes()))
        self.bulkRenameAction.triggered.connect(lambda: self.bulkRename(self.mainFileView.selectedIndexes()))
        self.deleteAction.triggered.connect(lambda: self.deleteItem(self.mainFileView.selectedIndexes()))
        self.cutAction.triggered.connect(lambda: self.copyFile(self.mainFileView.selectedIndexes(), cut=True))

        self.refreshAction.triggered.connect(self.listDirectories)
        self.goBackAction.triggered.connect(self.goBack)
        self.goForwardAction.triggered.connect(self.goForward)
        self.goUpAction.triggered.connect(self.goUp)

        self.sortAction.triggered.connect(self.sortHandler)

        self.mainFileView.doubleClicked.connect(lambda: self.openPath(self.mainFileView.selectedIndexes()))
        self.sideFileView.clicked.connect(lambda: self.openPath(self.sideFileView.selectedIndexes(), False))
        self.sideFileView.expanded.connect(lambda: self.sideFileView.resizeColumnToContents(0))

        self.mainFileView.itemDelegate().closeEditor.connect(self.editHandler)
        self.mainFileView.itemDropped.connect(self.dropMove)

        self.addressBar.returnPressed.connect(lambda: self.openPath(path=self.addressBar.text()))
        self.filterField.textChanged.connect(self.listDirectories)
        self.filterField.returnPressed.connect(lambda: self.listDirectories(self.filterField.text()))

    def bulkRenameDialog(self):
        dialog = QDialog()
        dialog.setWindowTitle('Bulk Rename')
        dialog.setWindowIcon(QIcon(':bulk_rename.png'))

        dialogLayout = QVBoxLayout()
        dialogLayout.addWidget(QLabel('Rename files in:'))
        pathLine = QLineEdit(str(self.currPath))
        pathLine.setReadOnly(True)
        dialogLayout.addWidget(pathLine)

        onlySelectedCheck = QCheckBox('Rename only selected files')
        dialogLayout.addWidget(onlySelectedCheck)

        extensionLayout = QHBoxLayout()
        extensionCheck = QCheckBox('Rename only files with extension:')
        extensionLine = QLineEdit()
        extensionLine.setEnabled(False)
        extensionLine.setPlaceholderText('Without dot, e.g. jpg')
        extensionLayout.addWidget(extensionCheck)
        extensionLayout.addWidget(extensionLine)
        dialogLayout.addLayout(extensionLayout)

        extensionCheck.stateChanged.connect(lambda: extensionLine.setEnabled(not extensionLine.isEnabled()))

        prefixLayout = QHBoxLayout()
        prefixLabel = QLabel('Prefix:')
        prefixLine = QLineEdit()
        prefixLabel.setFixedWidth(40)
        prefixLine.setFixedWidth(100)
        prefixLayout.addWidget(prefixLabel)
        prefixLayout.addWidget(prefixLine)
        prefixLayout.setAlignment(Qt.AlignLeft)
        dialogLayout.addLayout(prefixLayout)

        startNumLayout = QHBoxLayout()
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

        startNumCheck.stateChanged.connect(lambda: startNumSpin.setEnabled(not startNumSpin.isEnabled()))

        namePreviewLayout = QHBoxLayout()
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

        buttonBoxLayout = QHBoxLayout()
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

    def bulkRenameMsgBox(self, msgText):
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Warning)
        msgBox.setWindowIcon(QIcon(':bulk_rename.png'))
        msgBox.setText(msgText)
        msgBox.setWindowTitle("Bulk Rename")
        msgBox.setStandardButtons(QMessageBox.Ok)

        return msgBox.exec()

    def bulkRename(self, items: List[QModelIndex]):
        items = [self.currPath.joinpath(x.siblingAtColumn(0).data())
                 for i, x in enumerate(items) if i % len(self.modelHeaders) == 0]
        items = list(filter(lambda x: x.is_file(), items))
        illegalChars = {'<', '>', ':', '"', '/', '\\', '|', '?', '*'}
        while True:
            response, onlySelected, extension, prefix, startNumber = self.bulkRenameDialog()
            if not response:
                break
            if not items and onlySelected:
                self.bulkRenameMsgBox('No files were selected!')
                continue
            elif any((c in illegalChars) for c in prefix):
                self.bulkRenameMsgBox('Illegal characters in prefix!')
                continue
            fileFound = False
            for path in self.currPath.glob('*'):
                try:
                    if extension is not None and extension != path.suffix.lstrip('.'):
                        continue
                    if path.is_file() and (not onlySelected or path in items):
                        path.rename(self.currPath.joinpath(f'{prefix}{str(startNumber)}{path.suffix}'))
                        startNumber += 1
                        fileFound = True
                except FileExistsError:
                    self.bulkRenameMsgBox(f'File {path.name} already exists!')
                    self.statusBar.showMessage('Operation aborted!', 3000)
                    return
                finally:
                    self.listDirectories()
            if not fileFound:
                self.bulkRenameMsgBox('No suitable files in given directory!')
                continue
            break

        # def bulkRename(self, items: List[QModelIndex]):
        #     items = [self.currPath.joinpath(x.siblingAtColumn(0).data())
        #              for i, x in enumerate(items) if i % len(self.modelHeaders) == 0]
        #     items = list(filter(lambda x: x.is_file(), items))
        #     illegalChars = {'<', '>', ':', '"', '/', '\\', '|', '?', '*'}
        #     response, onlySelected, extension, prefix, startNumber = self.bulkRenameDialog()
        #     if not response:
        #         return
        #     elif not items and onlySelected:
        #         self.bulkRenameMsgBox('No files were selected!')
        #     elif any((c in illegalChars) for c in prefix):
        #         self.bulkRenameMsgBox('Illegal characters in prefix!')
        #     fileFound = False
        #     for path in self.currPath.glob('*'):
        #         if extension is not None and extension != path.suffix.lstrip('.'):
        #             continue
        #         if path.is_file() and (not onlySelected or path in items):
        #             path.rename(self.currPath.joinpath(f'{prefix}{str(startNumber)}{path.suffix}'))
        #             startNumber += 1
        #             fileFound = True
        #
        #     self.listDirectories()
        #
        # if not fileFound:
        #     self.bulkRenameMsgBox('No suitable files in given directory!')

    def sortDialog(self):
        dialog = QDialog()
        dialog.setFixedSize(300, 150)
        dialog.setWindowTitle('Sort')
        dialog.setWindowIcon(QIcon(':sort.png'))

        dialogLayout = QVBoxLayout()

        formLayout = QFormLayout()

        sortLabel = QLabel('Sort by:')
        sortComboBox = QComboBox()
        sortComboBox.addItems(self.modelHeaders)
        orderLabel = QLabel('Order:')
        orderRadioLayout = QVBoxLayout()
        orderRadioAsc = QRadioButton('ascending')
        orderRadioAsc.setChecked(True)
        orderRadioDesc = QRadioButton('descending')
        orderRadioLayout.addWidget(orderRadioAsc)
        orderRadioLayout.addWidget(orderRadioDesc)

        formLayout.addRow(sortLabel, sortComboBox)
        formLayout.addRow(orderLabel, orderRadioLayout)

        buttonBoxLayout = QHBoxLayout()
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

    def sortHandler(self):
        response, columnIndex, ascending = self.sortDialog()
        order = Qt.AscendingOrder if ascending else Qt.DescendingOrder
        if response:
            self.mainFileView.sortByColumn(columnIndex, order)

    def dropMove(self, point, selectedFiles):
        selectedFiles = [self.currPath.joinpath(x.data()) for i, x in enumerate(selectedFiles)
                         if i % len(self.modelHeaders) == 0]
        try:
            fname = self.mainFileView.indexAt(point).siblingAtColumn(0).data()
            dest = self.currPath.joinpath(fname)
            if dest.is_file():
                return
            duplicates = []
            for src in selectedFiles:
                dest = self.currPath.joinpath(fname).joinpath(src.name)
                if str(src) in str(dest):
                    return
                if dest.exists():
                    duplicates.append(dest)
            if duplicates:
                if self.overwriteFileDialog(duplicates) == QMessageBox.Cancel:
                    return
            for src in selectedFiles:
                dest = self.currPath.joinpath(fname).joinpath(src.name)
                if not src.exists():
                    raise FileNotFoundError
                if src.is_file():
                    shutil.move(str(src), str(dest))
                elif src.is_dir():
                    dir_util.copy_tree(str(src), str(dest))
                    shutil.rmtree(src)
        except FileNotFoundError:
            self.statusBar.showMessage('File not found!', 3000)
        except TypeError:
            pass
        finally:
            self.listDirectories()

    def listDirectories(self, filter=None):
        self.addressBar.setText(str(self.currPath))
        self.model.clear()
        self.updateMainFileView()
        fileIco = QIcon(':file_sm')
        folderIco = QIcon(':folder_sm')
        fileCutIco = QIcon(':file_sm_cut')
        folderCutIco = QIcon(':folder_sm_cut')
        for file in self.currPath.glob('*'):
            if self.isFolderHidden(file):
                continue
            if filter and filter.lower() not in file.name.lower():
                continue
            if file.is_dir():
                size = QStandardItem('')
                type = QStandardItem('Folder')
                icon = folderIco if Path(file) not in self.fileClipboard else folderCutIco
            else:
                size = QStandardItem(self.prettifySize(file.stat().st_size))
                type = QStandardItem(f'{file.suffix.upper()}{" " if file.suffix else ""}File')
                icon = fileIco if Path(file) not in self.fileClipboard else fileCutIco
            item = QStandardItem(icon, file.name)
            mod_date_str = dt.datetime.fromtimestamp(file.stat().st_mtime).strftime('%d.%m.%Y %H:%M')
            mod_date = QStandardItem(mod_date_str)
            self.model.appendRow([item, type, mod_date, size])
        self.mainFileView.sortByColumn(1, Qt.DescendingOrder)

    def isFolderHidden(self, path: Path):
        if os.name == 'nt':
            try:
                fileAttrs = win32api.GetFileAttributes(str(path))
                return fileAttrs & (win32con.FILE_ATTRIBUTE_HIDDEN | win32con.FILE_ATTRIBUTE_SYSTEM)
            except pywintypes.error:
                return False
        else:
            return path.name.startswith('.')

    def openPath(self, item=None, main=True, path=None, ignoreStack=False):
        if not item and not path:
            return
        if main and item:
            dir_name = self.model.data(item[0])
            path = self.currPath.parent if dir_name == '..' else self.currPath.joinpath(dir_name)
        elif not main and item:
            path = Path(self.sideModel.filePath(item[0]))
        elif type(path) is str:
            path = Path(path)

        if path.is_dir():
            try:
                os.listdir(str(path))  # used, because Path.glob() doesn't throw PermissionError
                if not ignoreStack and not path == self.currPath:
                    for _ in range(-1, self.stackIndex, -1):
                        self.pathStack.pop()
                    self.pathStack.append(path)
                    self.stackIndex = -1
                self.currPath = path
                self.listDirectories()
            except PermissionError:
                self.statusBar.showMessage('Access denied!', 3000)
        elif path.is_file():
            subprocess.Popen(str(path), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).poll()
        else:
            self.statusBar.showMessage('Invalid path!', 3000)
            self.listDirectories()

    def goBack(self):
        if abs(self.stackIndex) < len(self.pathStack):
            self.stackIndex -= 1
            self.openPath(path=self.pathStack[self.stackIndex], ignoreStack=True)

    def goForward(self):
        if self.stackIndex < -1:
            self.stackIndex += 1
            self.openPath(path=self.pathStack[self.stackIndex], ignoreStack=True)

    def goUp(self):
        self.openPath(path=self.currPath.parent)

    def addRowToModel(self, isDir):
        if isDir:
            self.model.appendRow(QStandardItem(QIcon(':folder_sm'), 'New Folder'))
            self.editItemType = 'folder'
        else:
            self.model.appendRow(QStandardItem(QIcon(':file_sm'), 'New File'))
            self.editItemType = 'file'
        self.mainFileView.scrollToBottom()
        self.editItem = self.model.item(self.model.rowCount() - 1)
        self.editItemNameBefore = self.editItem.text()
        index = self.model.indexFromItem(self.editItem)
        self.mainFileView.setCurrentIndex(index)
        self.mainFileView.edit(index)

    def editHandler(self):
        # nie mogę rozdzielić na dwie funkcje, bo editFinished signal
        # ewentualnie zrobić dwie następne funkcje i tu wrzucić
        if self.editItemType:
            try:
                name = self.editItem.text()
                path = self.currPath.joinpath(name)
                if self.editItemType == 'folder':
                    path.mkdir()
                elif self.editItemType == 'file':
                    if len(self.model.findItems(name)) > 1:
                        raise FileExistsError
                    with path.open('w+', encoding='utf-8'):
                        pass
                self.listDirectories()
                createdItem = self.model.findItems(name)
                index = self.model.indexFromItem(createdItem[0])
                self.mainFileView.scrollTo(index)
                self.mainFileView.setCurrentIndex(index)
            except FileExistsError:
                self.statusBar.showMessage('File/folder with that name already exists!', 3000)
                self.listDirectories()
        else:
            try:
                path = self.currPath.joinpath(self.editItemNameBefore)
                nameAfter = self.editItem.text()
                pathTo = self.currPath.joinpath(nameAfter)
                path.rename(pathTo)
                self.listDirectories()
                renamedItem = self.model.findItems(nameAfter)
                index = self.model.indexFromItem(renamedItem[0])
                self.mainFileView.scrollTo(index)
                self.mainFileView.setCurrentIndex(index)
            except FileExistsError:
                self.statusBar.showMessage('File/folder with that name already exists!', 3000)
                self.listDirectories()

    def renameTrigger(self, item):
        if not item:
            return
        item = item[0].siblingAtColumn(0)
        self.editItemNameBefore = item.data()
        self.editItem = self.model.itemFromIndex(item)
        self.editItemType = None
        self.mainFileView.edit(item)

    def deleteItem(self, items: List[QModelIndex]):
        if not items:
            return
        files = [x for i, x in enumerate(items) if i % len(self.modelHeaders) == 0]
        filename = files[0].data() if len(files) == 1 else None
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Warning)
        msgText = f"Are you sure to delete '{filename}'?" if filename else f"Are you sure to delete {len(files)} items?"
        msgBox.setText(msgText)
        msgBox.setWindowTitle("Confirm delete")
        msgBox.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)

        returnValue = msgBox.exec()
        if returnValue == QMessageBox.Ok:
            for file in files:
                path = self.currPath.joinpath(file.data())
                try:
                    if path.is_dir():
                        shutil.rmtree(path)
                    elif path.is_file():
                        os.remove(path)
                except FileNotFoundError:
                    self.statusBar.showMessage('Something went wrong!', 3000)
            self.listDirectories()

    def prettifySize(self, size):
        iteration = 0
        while size >= 1024:
            size /= 1024
            iteration += 1
        size = f'{size:.2f}'.rstrip('0').rstrip('.').rjust(6)
        return f'{size} {self.SIZES_SUFF[iteration]}'

    def copyPath(self, items):
        if len(items) == 0:
            return
        items = [x for i, x in enumerate(items) if i % len(self.modelHeaders) == 0]
        items = [str(self.currPath.joinpath(self.model.itemFromIndex(x).text())) for x in items]
        pyperclip.copy(', '.join(items))
        self.statusBar.showMessage('Path copied to clipboard!', 3000)

    def copyFile(self, items, cut=False):
        if len(items) == 0:
            return
        items = [x for i, x in enumerate(items) if i % len(self.modelHeaders) == 0]
        self.fileClipboard = [self.currPath.joinpath(self.model.itemFromIndex(x).text()) for x in items]
        self.fileClipboard.append(cut)
        if cut:
            folderCutIcon, fileCutIcon = QIcon(':folder_sm_cut'), QIcon(':file_sm_cut')
            for item in items:
                pathType = self.model.index(item.row(), 1, item.parent()).data()
                icon = folderCutIcon if pathType == 'Folder' else fileCutIcon
                self.model.itemFromIndex(item).setIcon(icon)
            self.listDirectories()
        self.pasteFileAction.setEnabled(True)
        self.statusBar.showMessage('File copied to clipboard!', 3000)

    def overwriteFileDialog(self, duplicates):
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

    def pasteFile(self):
        if self.fileClipboard:
            cut = self.fileClipboard.pop()
            filenames = [x.name for x in self.fileClipboard]
            destPaths = [self.currPath.joinpath(x) for x in filenames]
            try:
                duplicates = []
                for src, dest in zip(self.fileClipboard, destPaths):
                    if src == dest:
                        raise shutil.SameFileError
                    if dest in self.currPath.glob('*'):
                        duplicates.append(dest)
                if duplicates:
                    if self.overwriteFileDialog(duplicates) == QMessageBox.Cancel:
                        self.fileClipboard.clear()
                        self.pasteFileAction.setEnabled(False)
                        return
                for src, dest in zip(self.fileClipboard, destPaths):
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
                self.statusBar.showMessage('File pasted!', 3000)
                self.fileClipboard.clear()
                self.pasteFileAction.setEnabled(False)
            except shutil.SameFileError:
                self.statusBar.showMessage('You cannot overwrite the same file!', 3000)
                self.fileClipboard.clear()
            except PermissionError:
                self.statusBar.showMessage('No permission to copy the file!', 3000)
                self.fileClipboard.clear()
            except FileNotFoundError:
                self.statusBar.showMessage('Cannot find the source file!', 3000)
                self.fileClipboard.clear()
            finally:
                self.listDirectories()


def main():
    app = QApplication(sys.argv)
    window = FileManager()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
