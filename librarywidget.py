# Copyright 2017 by Kurt Rathjen. All Rights Reserved.
#
# This library is free software: you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Lesser General Public License for more details.
# You should have received a copy of the GNU Lesser General Public
# License along with this library. If not, see <http://www.gnu.org/licenses/>.

import re
import os
import time
import logging

from studioqt import QtGui
from studioqt import QtCore
from studioqt import QtWidgets

import studioqt
import studiolibrary

__all__ = ["LibraryWidget"]

logger = logging.getLogger(__name__)


class PreviewFrame(QtWidgets.QFrame):
    pass


class FoldersFrame(QtWidgets.QFrame):
    pass


class GlobalSignal(QtCore.QObject):
    """
    Triggered for all library instance.
    """
    debugModeChanged = QtCore.Signal(object, object)
    folderSelectionChanged = QtCore.Signal(object, object)


class LibraryWidget(QtWidgets.QWidget):

    _instances = {}

    DEFAULT_NAME = "Default"
    HOME_PATH = os.getenv('APPDATA') or os.getenv('HOME')

    DATABASE_PATH = "{path}/.studiolibrary/items.json"
    SETTINGS_PATH = os.path.join(HOME_PATH, "StudioLibrary", "LibraryWidget.json")

    TRASH_ENABLED = True
    THEMES_MENU_ENABLED = True
    RECURSIVE_SEARCH_ENABLED = False
    DEFAULT_GROUP_BY_COLUMNS = ["Category", "Modified", "Type"]

    # Still in development
    DPI_ENABLED = False
    DPI_MIN_VALUE = 80
    DPI_MAX_VALUE = 250

    globalSignal = GlobalSignal()

    # Local signal
    loaded = QtCore.Signal()
    lockChanged = QtCore.Signal(object)
    debugModeChanged = QtCore.Signal(object)

    itemRenamed = QtCore.Signal(str, str)
    itemSelectionChanged = QtCore.Signal(object)

    folderRenamed = QtCore.Signal(str, str)
    folderSelectionChanged = QtCore.Signal(object)

    @classmethod
    def instances(cls):
        """
        Return all the library instances that have been initialised.

        :rtype: list[LibraryWidget] 
        """
        return cls._instances.values()

    @classmethod
    def instance(cls, name=None, path=None):
        """
        Return the library widget for the given path.

        :type name: str
        :type path: str
        :rtype: CatalogWidget
        """
        name = name or cls.DEFAULT_NAME

        w = cls._instances.get(name)

        if not w:
            w = cls(name=name, path=path)
            cls._instances[name] = w

        return w

    def __init__(self, parent=None, name=None, path=None):
        """
        Return the a new instance of the Library Widget.

        :type name: str
        :type path: str
        """
        QtWidgets.QWidget.__init__(self, parent)

        self.setObjectName("studiolibrary")

        studiolibrary.logScreen("MainWindow")

        resource = studiolibrary.resource()
        self.setWindowIcon(resource.icon("icon_black"))

        self._dpi = 1.0
        self._name = name or self.DEFAULT_NAME
        self._theme = None
        self._database = None
        self._isDebug = False
        self._isLocked = False
        self._isLoaded = False
        self._previewWidget = None
        self._currentItem = None
        self._itemLoaderEnabled = True

        self._superusers = None
        self._lockRegExp = None
        self._unlockRegExp = None

        self._trashEnabled = self.TRASH_ENABLED
        self._recursiveSearchEnabled = self.RECURSIVE_SEARCH_ENABLED

        self._itemsHiddenCount = 0
        self._itemsVisibleCount = 0

        self._isTrashFolderVisible = False
        self._foldersWidgetVisible = True
        self._previewWidgetVisible = True
        self._statusBarWidgetVisible = True

        # --------------------------------------------------------------------
        # Create Widgets
        # --------------------------------------------------------------------

        self._foldersFrame = FoldersFrame(self)
        self._previewFrame = PreviewFrame(self)

        self._itemsWidget = studioqt.CombinedWidget(self)

        tip = "Search all current items."
        self._searchWidget = studioqt.SearchWidget(self)
        self._searchWidget.setToolTip(tip)
        self._searchWidget.setStatusTip(tip)

        self._statusWidget = studioqt.StatusWidget(self)
        self._menuBarWidget = studioqt.MenuBarWidget()
        self._foldersWidget = studioqt.FoldersWidget(self)

        self.setMinimumWidth(5)
        self.setMinimumHeight(5)

        # --------------------------------------------------------------------
        # Setup the menu bar buttons
        # --------------------------------------------------------------------

        name = "New Item"
        icon = studioqt.resource.icon("add")
        tip = "Add a new item to the selected folder"
        self.addMenuBarAction(name, icon, tip, callback=self.showNewMenu, side="Left")

        name = "Item View"
        icon = studioqt.resource.icon("view_settings")
        tip = "Change the style of the item view"
        self.addMenuBarAction(name, icon, tip, callback=self.showItemViewMenu)

        name = "Group By"
        icon = studioqt.resource.icon("groupby")
        tip = "Group the current items in the view by column"
        self.addMenuBarAction(name, icon, tip, callback=self.showGroupByMenu)

        name = "Sort By"
        icon = studioqt.resource.icon("sortby")
        tip = "Sort the current items in the view by column"
        self.addMenuBarAction(name, icon, tip, callback=self.showSortByMenu)

        name = "View"
        icon = studioqt.resource.icon("view")
        tip = "Choose to show/hide both the preview and navigation pane. " \
              "Click + CTRL will hide the menu bar as well."
        self.addMenuBarAction(name, icon, tip, callback=self.toggleView)

        name = "Settings"
        icon = studioqt.resource.icon("settings")
        tip = "Settings menu"
        self.addMenuBarAction(name, icon, tip, callback=self.showSettingsMenu)

        self._menuBarWidget.layout().insertWidget(1, self._searchWidget)

        # -------------------------------------------------------------------
        # Setup Layout
        # -------------------------------------------------------------------

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 0)
        self._previewFrame.setLayout(layout)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 0)

        self._foldersFrame.setLayout(layout)
        self._foldersFrame.layout().addWidget(self._foldersWidget)

        self._splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        self._splitter.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Expanding)
        self._splitter.setHandleWidth(2)
        self._splitter.setChildrenCollapsible(False)

        self._splitter.insertWidget(0, self._foldersFrame)
        self._splitter.insertWidget(1, self._itemsWidget)
        self._splitter.insertWidget(2, self._previewFrame)

        self._splitter.setStretchFactor(0, False)
        self._splitter.setStretchFactor(1, True)
        self._splitter.setStretchFactor(2, False)

        self.layout().addWidget(self._menuBarWidget)
        self.layout().addWidget(self._splitter)
        self.layout().addWidget(self._statusWidget)

        vbox = QtWidgets.QVBoxLayout()
        self._previewFrame.setLayout(vbox)
        self._previewFrame.layout().setSpacing(0)
        self._previewFrame.layout().setContentsMargins(0, 0, 0, 0)
        self._previewFrame.setMinimumWidth(5)

        # -------------------------------------------------------------------
        # Setup Connections
        # -------------------------------------------------------------------

        searchWidget = self.searchWidget()
        searchWidget.searchChanged.connect(self._searchChanged)

        studiolibrary.LibraryItem.saved.connect(self._itemSaved)
        studiolibrary.LibraryItem.saving.connect(self._itemSaving)

        itemsWidget = self.itemsWidget()
        itemsWidget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        itemsWidget.itemMoved.connect(self._itemMoved)
        itemsWidget.itemSelectionChanged.connect(self._itemSelectionChanged)
        itemsWidget.customContextMenuRequested.connect(self.showItemsContextMenu)
        itemsWidget.treeWidget().setValidGroupByColumns(self.DEFAULT_GROUP_BY_COLUMNS)

        folderWidget = self.foldersWidget()
        folderWidget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        folderWidget.itemDropped.connect(self._folderDropped)
        folderWidget.itemRenamed.connect(self._folderRenamed)
        folderWidget.itemSelectionChanged.connect(self._folderSelectionChanged)
        folderWidget.customContextMenuRequested.connect(self.showFolderContextMenu)

        self.folderSelectionChanged.connect(self.updateLock)

        self.updateViewButton()

        path = path or self.pathFromSettings()

        if os.path.isdir(path):
            self.setRootPath(path)
        else:
            self.showWelomeDialog()

    def _folderRenamed(self, src, dst):
        """
        Triggered when a folder has been renamed from the folder widget.

        :str src: str
        :str dst: str
        :rtype: None
        """
        db = self.database()
        db.renameFolder(src, dst)

        self.loadItemData()
        self.folderRenamed.emit(src, dst)

    def _itemSelectionChanged(self):
        """
        Triggered when an item is selected or deselected.

        :rtype: None
        """
        item = self.itemsWidget().selectedItem()

        self.setPreviewWidgetFromItem(item)

        self.itemSelectionChanged.emit(item)

    def _folderSelectionChanged(self):
        """
        Triggered when an item is selected or deselected.

        :rtype: None
        """
        self.loadItems()
        path = self.selectedFolderPath()
        self.folderSelectionChanged.emit(path)
        self.globalSignal.folderSelectionChanged.emit(self, path)

    def _itemMoved(self, item):
        """
        Triggered when an item has been moved.

        :type item: studiolibrary.LibraryItem
        :rtype: None
        """
        self.saveCustomOrder()

    def _folderDropped(self, event):
        """
        Triggered when an item has been dropped on the folder widget.

        :type event: list[studiolibrary.LibraryItem]
        :rtype: None
        """
        mimeData = event.mimeData()

        if mimeData.hasUrls():
            folder = self.selectedFolder()
            items = self.createItemsFromUrls(mimeData.urls())

            for item in items:

                # Check if the item is moving to another folder.
                if folder.path() != item.dirname():
                    self.moveItemsToFolder(items, folder=folder)
                    break

    def _itemSaving(self, item):
        """
        Triggered when an item is saving.

        :type item: studiolibrary.LibraryItem
        :rtype: None
        """
        if self.path() in item.path():
            if item.exists():
                self.showItemExistsDialog(item)

    def _itemSaved(self, item):
        """
        Triggered when an item has finished saving.

        :type item: studiolibrary.LibraryItem
        :rtype: None
        """
        folder = self.selectedFolder()

        if folder and folder.path() == item.dirname():
            path = item.path()
            self.loadItems()
            self.selectPath(path)

    def statusWidget(self):
        """
        :rtype: StatusWidget
        """
        return self._statusWidget

    def searchWidget(self):
        """
        :rtype: SearchWidget
        """
        return self._searchWidget

    def menuBarWidget(self):
        """
        :rtype: MenuBarWidget
        """
        return self._menuBarWidget

    def name(self):
        """
        Return the name of the library.

        :rtype: str 
        """
        return self._name

    def path(self):
        """
        Return the root path for the library.

        :rtype: str
        """
        path = self.foldersWidget().rootPath()

        if path == ".":
            path = ""

        return path

    def pathFromSettings(self):
        """
        Return the root path from the settings file.

        :rtype: str 
        """
        settings = self.readSettings()
        return settings.get("path", "")

    def setPath(self, path):
        """
        Convenience method to set the root path for the library.

        :type path: str
        :rtype: None
        """
        self.setRootPath(path)

    def setRootPath(self, path):
        """
        Set the root path for the library.

        :type path: str
        :rtype: None
        """
        if path:
            trashPath = self.trashPath()
            folderWidget = self.foldersWidget()

            path_ = studiolibrary.formatPath(path, self.DATABASE_PATH)
            self.setDatabasePath(path_)

            folderWidget.clearSelection()
            folderWidget.setRootPath(path)
            folderWidget.setIgnoreFilter(self.folderIgnoreFilter)
            folderWidget.setFolderOrderIndex(trashPath, 0)
        else:
            self.setError("Error: No path found! Please change the path from the settings menu!")

        self.updateWindowTitle()

    def showWelomeDialog(self):
        """
        Show a welcome dialog for setting up a dialog.

        :rtype: None
        """
        name = self.name()

        title = "Studio Library - {} - {} "
        title = title.format(studiolibrary.version(), name)

        text = """Welcolme! Before you get started please choose a folder location for storing the data.
A network folder is recommended for sharing within a studio."""

        dialog = QtWidgets.QMessageBox(None)
        dialog.setWindowTitle(title)
        dialog.setText(text)
        dialog.addButton("Browse", QtWidgets.QMessageBox.AcceptRole)
        dialog.exec_()

        self.showChangePathDialog()

    def showChangePathDialog(self):
        """
        Show a path browser for changing the root path.

        :rtype: None
        """
        path = self._changePathDialog()

        if not path:
            self.setRootPath(path)

    def _changePathDialog(self):
        """
        Open the file dialog for setting a new path.

        :rtype: str
        """
        path = self.path()
        title = "Choose the root location"

        if not path:
            from os.path import expanduser
            path = expanduser("~")

        path = QtWidgets.QFileDialog.getExistingDirectory(self, title, path)
        path = path.replace("\\", "/")

        if path:
            self.setPath(path)
            self.saveSettings()

        return path

    # -----------------------------------------------------------------
    # Methods for the navigation widget
    # -----------------------------------------------------------------

    def foldersWidget(self):
        """
        :rtype: studiolibrary.FoldersWidget
        """
        return self._foldersWidget

    def folderIgnoreFilter(self, path):
        """
        Return False if path have to be ignored in folders widget

        :rtype: bool
        """
        ignoreFilter = ['.', '.studiolibrary', ".mayaswatches"]

        if not self.isTrashFolderVisible():
            ignoreFilter.append('trash')

        for f in ignoreFilter:
            if path.endswith(f):
                return False

        for cls in self.itemClasses():
            if cls.isPathSuitable(path):
                return False

        return True

    def showCreateFolderDialog(self):
        """
        :rtype: None
        """
        try:
            self.foldersWidget().showCreateDialog(parent=self)
        except Exception, e:
            self.setError(e.message)
            raise

    def selectedFolderPath(self):
        """
        Return the selected folder paths.

        :rtype: list[str] 
        """
        folder = self.selectedFolder()
        if folder:
            return folder.path()

    def selectedFolder(self):
        """
        Return the selected folder.

        :rtype: studioqt.FolderItem
        """
        folders = self.selectedFolders()
        if folders:
            return folders[0]
        return None

    def selectedFolders(self):
        """
        Return the selected folder items.

        :rtype: list[studioqt.FolderItem] 
        """
        return self.foldersWidget().selectedFolders()

    def selectFolderPaths(self, folders):
        """
        Select the given folder paths.

        :type folders: list[str] 
        :rtype: None 
        """
        self.foldersWidget().selectPaths(folders)

    # -----------------------------------------------------------------
    # Methods for the items widget
    # -----------------------------------------------------------------

    def itemsWidget(self):
        """
        Return the widget the contains all the items.

        :rtype: studioqt.CombinedWidget
        """
        return self._itemsWidget

    def selectPath(self, path):
        """
        Select the item with the given path.

        :type path: str
        :rtype: None
        """
        self.selectPaths([path])

    def selectPaths(self, paths):
        """
        Select items with the given paths.

        :type paths: list[str]
        :rtype: None
        """
        selection = self.selectedItems()

        self.itemsWidget().clearSelection()
        self.itemsWidget().selectPaths(paths)

        if self.selectedItems() != selection:
            self._itemSelectionChanged()

    def selectItems(self, items):
        """
        Select the given items.

        :type items: list[studiolibrary.LibraryItem] 
        :rtype: None 
        """
        paths = [item.path() for item in items]
        self.selectPaths(paths)

    def selectedItems(self):
        """
        Return the selected items.

        :rtype: list[studiolibrary.LibraryItem] 
        """
        return self._itemsWidget.selectedItems()

    def clearItems(self):
        """
        Remove all the loaded items.

        :rtype: list[studiolibrary.LibraryItem]
        """
        self.itemsWidget().clear()

    def items(self):
        """
        Return all the loaded items.

        :rtype: list[studiolibrary.LibraryItem]
        """
        return self.itemsWidget().items()

    def setItems(self, items, sortEnabled=False):
        """
        Set the items for the library widget.

        :rtype: list[studiolibrary.LibraryItem]
        """
        selectedItems = self.selectedItems()

        self.itemsWidget().setItems(items, sortEnabled=sortEnabled)

        self.loadItemData()

        if selectedItems:
            self.selectItems(selectedItems)

        self.refreshSearch()

    def setItemLoaderEnabled(self, value):
        """
        :type value: bool
        :rtype: None
        """
        self._itemLoaderEnabled = value

    def itemLoaderEnabled(self):
        """
        :rtype: func
        """
        return self._itemLoaderEnabled

    def createItems(self):
        """
        Return a new instance of the items to be shown.

        :rtype: list[studiolibrary.LibraryItem]
        """
        paths = self.foldersWidget().selectedPaths()
        depth = 1

        if self.isRecursiveSearchEnabled():
            depth = 3

        items = list(self.findItemsInFolders(paths, depth))

        return items

    def createItemsFromUrls(self, urls):
        """
        Return a new instance of the items to be shown from the given urls.

        :rtype: list[studiolibrary.LibraryItem]
        """
        items = self.itemsFromUrls(urls)

        return items

    @studioqt.showWaitCursor
    def loadItems(self):

        """Reload the items widget."""
        if not self.itemLoaderEnabled():
            logger.debug("Loader disabled!")
            return

        elapsedTime = time.time()

        items = self.createItems()
        self.setItems(items, sortEnabled=False)

        elapsedTime = time.time() - elapsedTime
        self.setLoadedMessage(elapsedTime)

        logger.debug("Loaded items")

    @studioqt.showWaitCursor
    def reloadFolders(self):
        """Reload the folder widget."""
        self.foldersWidget().reload()
        self.foldersWidget().setIgnoreFilter(self.folderIgnoreFilter)

    # -----------------------------------------------------------------
    # Support for custom context menus
    # -----------------------------------------------------------------

    def addMenuBarAction(self, name, icon, tip, side="Right", callback=None):
        """
        Add a button/action to menu bar widget.

        :type name: str
        :type icon: QtWidget.QIcon
        :param tip: str
        :param side: str
        :param callback: func
        :rtype: QtWidget.QAction
        """
        return self.menuBarWidget().addAction(
            name=name,
            icon=icon,
            tip=tip,
            side=side,
            callback=callback,
        )

    def showGroupByMenu(self):
        """
        Show the group by menu at the group button.

        :rtype: None
        """
        menu = self.itemsWidget().createGroupByMenu()
        widget = self.menuBarWidget().findToolButton("Group By")

        point = widget.mapToGlobal(QtCore.QPoint(0, widget.height()))
        menu.exec_(point)

    def showSortByMenu(self):
        """
        Show the sort by menu at the sort button.

        :rtype: None
        """
        menu = self.itemsWidget().createSortByMenu()
        widget = self.menuBarWidget().findToolButton("Sort By")

        point = widget.mapToGlobal(QtCore.QPoint(0, widget.height()))
        menu.exec_(point)

    def showItemViewMenu(self):
        """
        Show the item settings menu.

        :rtype: None
        """
        menu = self.itemsWidget().createItemSettingsMenu()
        widget = self.menuBarWidget().findToolButton("Item View")

        point = widget.mapToGlobal(QtCore.QPoint(0, widget.height()))
        menu.exec_(point)

    def createNewMenu(self):
        """
        Return the new menu for adding new folders and items.

        :rtype: QtWidgets.QMenu
        """
        color = self.iconColor()

        icon = studiolibrary.resource().icon("add", color=color)
        menu = QtWidgets.QMenu(self)
        menu.setIcon(icon)
        menu.setTitle("New")

        icon = studiolibrary.resource().icon("folder", color=color)
        action = QtWidgets.QAction(icon, "Folder", menu)
        action.triggered.connect(self.showCreateFolderDialog)
        menu.addAction(action)

        separator = QtWidgets.QAction("", menu)
        separator.setSeparator(True)
        menu.addAction(separator)

        for itemClass in self.itemClasses():
            action = itemClass.createAction(menu, self)

            if action:
                icon = studioqt.Icon(action.icon())
                icon.setColor(self.iconColor())

                action.setIcon(icon)
                menu.addAction(action)

        return menu

    def createSettingsMenu(self):
        """
        Return the settings menu for changing the library widget.

        :rtype: studioqt.Menu
        """
        menu = studioqt.Menu("", self)
        menu.setTitle("Settings")

        if self.DPI_ENABLED:
            action = studioqt.SliderAction("Dpi", menu)
            dpi = self.dpi() * 100.0
            action.slider().setRange(self.DPI_MIN_VALUE, self.DPI_MAX_VALUE)
            action.slider().setValue(dpi)
            action.valueChanged.connect(self._dpiSliderChanged)
            menu.addAction(action)

        action = QtWidgets.QAction("Change Path", menu)
        action.triggered.connect(self.showChangePathDialog)
        menu.addAction(action)

        if self.THEMES_MENU_ENABLED:
            menu.addSeparator()
            themesMenu = studioqt.ThemesMenu(menu)
            themesMenu.setCurrentTheme(self.theme())
            themesMenu.themeTriggered.connect(self.setTheme)
            menu.addMenu(themesMenu)

        menu.addSeparator()

        action = QtWidgets.QAction("Show menu", menu)
        action.setCheckable(True)
        action.setChecked(self.isMenuBarWidgetVisible())
        action.triggered[bool].connect(self.setMenuBarWidgetVisible)
        menu.addAction(action)

        action = QtWidgets.QAction("Show folders", menu)
        action.setCheckable(True)
        action.setChecked(self.isFoldersWidgetVisible())
        action.triggered[bool].connect(self.setFoldersWidgetVisible)
        menu.addAction(action)

        action = QtWidgets.QAction("Show preview", menu)
        action.setCheckable(True)
        action.setChecked(self.isPreviewWidgetVisible())
        action.triggered[bool].connect(self.setPreviewWidgetVisible)
        menu.addAction(action)

        action = QtWidgets.QAction("Show status", menu)
        action.setCheckable(True)
        action.setChecked(self.isStatusBarWidgetVisible())
        action.triggered[bool].connect(self.setStatusBarWidgetVisible)
        menu.addAction(action)

        if self.trashEnabled():
            menu.addSeparator()
            action = QtWidgets.QAction("Show Trash Folder", menu)
            action.setEnabled(self.trashFolderExists())
            action.setCheckable(True)
            action.setChecked(self.isTrashFolderVisible())
            action.triggered[bool].connect(self.setTrashFolderVisible)
            menu.addAction(action)

        menu.addSeparator()

        action = QtWidgets.QAction("Enable Recursive Search", menu)
        action.setCheckable(True)
        action.setChecked(self.isRecursiveSearchEnabled())
        action.triggered[bool].connect(self.setRecursiveSearchEnabled)
        menu.addAction(action)

        menu.addSeparator()

        viewMenu = self.itemsWidget().createSettingsMenu()
        menu.addMenu(viewMenu)

        menu.addSeparator()

        action = QtWidgets.QAction("Debug mode", menu)
        action.setCheckable(True)
        action.setChecked(self.isDebug())
        action.triggered[bool].connect(self.setDebugMode)
        menu.addAction(action)

        action = QtWidgets.QAction("Help", menu)
        action.triggered.connect(self.help)
        menu.addAction(action)

        return menu

    def showNewMenu(self):
        """
        Creates and shows the new menu at the new action button.

        :rtype: QtWidgets.QAction
        """
        menu = self.createNewMenu()

        point = self.menuBarWidget().rect().bottomLeft()
        point = self.menuBarWidget().mapToGlobal(point)

        menu.show()
        return menu.exec_(point)

    def showSettingsMenu(self):
        """
        Show the settings menu at the current cursor position.

        :rtype: QtWidgets.QAction
        """
        menu = self.createSettingsMenu()

        point = self.menuBarWidget().rect().bottomRight()
        point = self.menuBarWidget().mapToGlobal(point)

        # Align menu to the left of the cursor.
        menu.show()
        x = point.x() - menu.width()
        point.setX(x)

        return menu.exec_(point)

    def showFolderContextMenu(self, pos=None):
        """
        Show the folder context menu at the current cursor position.

        :type pos: None or QtCore.QPoint
        :rtype: QtWidgets.QAction
        """
        menu = self.createFolderContextMenu()

        point = QtGui.QCursor.pos()
        point.setX(point.x() + 3)
        point.setY(point.y() + 3)
        action = menu.exec_(point)
        menu.close()

        return action

    def createFolderContextMenu(self):
        """
        Return the folder menu for editing the selected folders.

        :rtype: QtWidgets.QMenu
        """
        menu = QtWidgets.QMenu(self)

        if self.isLocked():
            action = menu.addAction("Locked")
            action.setEnabled(False)
        else:

            menu.addMenu(self.createNewMenu())

            folders = self.selectedFolders()

            if folders:
                m = self.foldersWidget().createEditMenu(menu)
                menu.addMenu(m)

            menu.addSeparator()
            menu.addMenu(self.createSettingsMenu())

        return menu

    def showItemsContextMenu(self, pos=None):
        """
        Show the item context menu at the current cursor position.

        :type pos: QtGui.QPoint
        :rtype QtWidgets.QAction
        """
        items = self.itemsWidget().selectedItems()

        menu = self.createItemContextMenu(items)

        point = QtGui.QCursor.pos()
        point.setX(point.x() + 3)
        point.setY(point.y() + 3)
        action = menu.exec_(point)
        menu.close()

        return action

    def createItemContextMenu(self, items):
        """
        Return the item context menu for the given items.

        :type items: list[studiolibrary.LibraryItem]
        :rtype: studiolibrary.ContextMenu
        """
        menu = studioqt.ContextMenu(self)

        item = None

        if items:
            item = items[-1]
            item.contextMenu(menu)

        if not self.isLocked():
            menu.addMenu(self.createNewMenu())

            if item:
                editMenu = studioqt.ContextMenu(menu)
                editMenu.setTitle("Edit")
                menu.addMenu(editMenu)

                item.contextEditMenu(editMenu)

                if self.trashEnabled():
                    editMenu.addSeparator()

                    action = QtWidgets.QAction("Move to trash", editMenu)
                    action.setEnabled(self.isTrashEnabled())
                    action.triggered.connect(self.trashSelectedItemsDialog)
                    editMenu.addAction(action)

        menu.addSeparator()
        menu.addMenu(self.createSettingsMenu())

        return menu

    # -------------------------------------------------------------------
    # Support for reading and writing to the item database
    # -------------------------------------------------------------------

    def database(self):
        """
        Return the database object.

        :rtype: studiolibrary.Database
        """
        return self._database

    def databasePath(self):
        """
        Return the database location on disc.

        :rtype: str 
        """
        return self.database().path()

    def setDatabasePath(self, path):
        """
        Set the database path for the catalog.

        :type path: str
        :rtype: None 
        """
        self._database = studiolibrary.Database(path)

    def loadItemData(self):
        """
        Load the item data to the current items.

        :rtype: None
        """
        logger.debug("Loading item data")

        db = self.database()
        data = db.read()

        try:
            self.itemsWidget().setItemData(data)
        except Exception, msg:
            logger.exception(msg)

        self.refreshSearch()
        self.itemsWidget().refreshSortBy()

    def saveItemData(self, columns):
        """
        Save the given column data for the current items.

        :rtype: None
        """
        logger.debug("Saving item data")

        data = self.itemsWidget().itemData(columns)

        db = self.database()
        db.update(data)

        self.loadItemData()

    def saveCustomOrder(self):
        """
        Convenience method for saving the custom order.

        :rtype:  None
        """
        self.saveItemData(["Custom Order"])

    # -------------------------------------------------------------------
    # Support for moving items with drag and drop
    # -------------------------------------------------------------------

    def moveItemsDialog(self, parent=None):
        """
        :type parent: QtWidgets.QWidget
        :rtype: QtWidgets.QMessageBox
        """
        parent = parent or self

        msgBox = QtWidgets.QMessageBox(parent)
        msgBox.setWindowTitle("Move or Copy items?")
        msgBox.setText('Would you like to copy or move the selected item/s?')
        msgBox.addButton('Copy', QtWidgets.QMessageBox.AcceptRole)
        msgBox.addButton('Move', QtWidgets.QMessageBox.AcceptRole)
        msgBox.addButton('Cancel', QtWidgets.QMessageBox.RejectRole)

        return msgBox

    def moveItemsToFolder(self, items, folder):
        """
        :type items: list[studiolibrary.LibraryItem]
        :type folder: studiolibrary.Folder
        :rtype: None
        """
        Copy = 0
        Move = 1
        Cancel = 2
        movedItems = []

        dialog = self.moveItemsDialog()
        action = dialog.exec_()
        dialog.close()

        if action == Cancel:
            return

        self.itemsWidget().clearSelection()

        try:
            for item in items:

                path = folder.path() + "/" + item.name()

                if action == Copy:
                    item.copy(path)

                elif action == Move:
                    item.rename(path)

                movedItems.append(item)

        except Exception, e:
            message = str(e)
            logger.exception(message)
            self.criticalDialog(message)
            raise
        finally:
            self.itemsWidget().addItems(movedItems)
            self.selectItems(movedItems)
            self.refreshLibraryWidgets()

    def showItemExistsDialog(self, item):
        """
        :type item: studiolibrary.LibraryItem
        :rtype: None
        """
        path = item.path()
        items = [item]
        title = "Warning"
        message = 'Item already exists! Would you like to move the existing item "{name}" to the trash?'
        message = message.format(name=item.name())

        result = self.trashItemsDialog(items, title=title, message=message)

        if result == QtWidgets.QMessageBox.Cancel:
            item.setErrorString("Item was not saved! Saving was canceled.")
        elif result != QtWidgets.QMessageBox.Yes:
            item.setErrorString(
                "Item was not saved! You cannot save over an existsing item.")

        item.setPath(path)

    # -----------------------------------------------------------------------
    # Support for search
    # -----------------------------------------------------------------------

    def isPreviewWidgetVisible(self):
        """
        :rtype: bool
        """
        return self._previewWidgetVisible

    def isFoldersWidgetVisible(self):
        """
        :rtype: bool
        """
        return self._foldersWidgetVisible

    def isStatusBarWidgetVisible(self):
        """
        :rtype: bool
        """
        return self._statusBarWidgetVisible

    def isMenuBarWidgetVisible(self):
        """
        :rtype: bool
        """
        return self.menuBarWidget().isExpanded()

    def setPreviewWidgetVisible(self, value):
        """
        :type value: bool
        """
        value = bool(value)
        self._previewWidgetVisible = value

        if value:
            self._previewFrame.show()
        else:
            self._previewFrame.hide()

        self.updateViewButton()

    def setFoldersWidgetVisible(self, value):
        """
        :type value: bool
        """
        value = bool(value)
        self._foldersWidgetVisible = value

        if value:
            self._foldersFrame.show()
        else:
            self._foldersFrame.hide()

        self.updateViewButton()

    def setMenuBarWidgetVisible(self, value):
        """
        :type value: bool
        """
        value = bool(value)

        if value:
            self.menuBarWidget().expand()
        else:
            self.menuBarWidget().collapse()

    def setStatusBarWidgetVisible(self, value):
        """
        :type value: bool
        """
        value = bool(value)

        self._statusBarWidgetVisible = value
        if value:
            self.statusWidget().show()
        else:
            self.statusWidget().hide()

    # -----------------------------------------------------------------------
    # Support for search
    # -----------------------------------------------------------------------

    def filterItems(self, items):
        """
        Filter the given items using the search filter.

        :rtype: list[studiolibrary.LibraryItem]
        """
        searchFilter = self.searchWidget().searchFilter()

        column = self.itemsWidget().treeWidget().columnFromLabel(
            "Search Order")

        for item in items:
            if searchFilter.match(item.searchText()):
                item.setText(column, str(searchFilter.matches()))
                yield item

        if self.itemsWidget().sortColumn() == column:
            self.itemsWidget().refreshSortBy()

    def setSearchText(self, text):
        """
        Set the search widget text..

        :type text: str
        :rtype: None
        """
        self.searchWidget().setText(text)

    def refreshSearch(self):
        """
        Refresh the search results.

        :rtype: None
        """
        self._searchChanged()

    def itemsVisibleCount(self):
        """
        Return the number of items visible.

        :rtype:  int
        """
        return self._itemsVisibleCount

    def itemsHiddenCount(self):
        """
        Return the number of items hidden.

        :rtype:  int
        """
        return self._itemsHiddenCount

    def _searchChanged(self):
        """
        Triggered when the search widget has changed.

        :rtype: None
        """
        t = time.time()

        items = self.items()

        validItems = list(self.filterItems(items))
        invalidItems = list(set(items) - set(validItems))

        self._itemsVisibleCount = len(validItems)
        self._itemsHiddenCount = len(invalidItems)

        self.itemsWidget().setItemsHidden(validItems, False)
        self.itemsWidget().setItemsHidden(invalidItems, True)

        item = self.itemsWidget().selectedItem()

        if not item or item.isHidden():
            self.itemsWidget().clearSelection()

        if item:
            self.itemsWidget().scrollToItem(item)

        t = time.time() - t

        plural = ""
        if self._itemsVisibleCount > 1:
            plural = "s"

        self.itemsWidget().treeWidget().refreshGroupBy()

        msg = "Found {0} item{1} in {2:.3f} seconds."
        msg = msg.format(self._itemsVisibleCount, plural, t)
        self.statusWidget().setInfo(msg)

    # -----------------------------------------------------------------------
    # Support for custom preview widgets
    # -----------------------------------------------------------------------

    def setCreateWidget(self, widget):
        """
        :type widget: QtWidgets.QWidget
        :rtype: None
        """
        self.setPreviewWidgetVisible(True)
        self.itemsWidget().clearSelection()
        self.setPreviewWidget(widget)

    def clearPreviewWidget(self):
        """
        Set the default preview widget.
        """
        widget = QtWidgets.QWidget(None)
        self.setPreviewWidget(widget)

    def setPreviewWidgetFromItem(self, item):
        """
        :type item: studiolibrary.LibraryItem
        :rtype: None
        """
        if self._currentItem == item:
            logger.debug("The current item preview widget is already set.")
            return

        self._currentItem = item

        if item:
            try:
                item.showPreviewWidget(self)
            except Exception, msg:
                self.setError(msg)
                raise
        else:
            self.clearPreviewWidget()

    def previewWidget(self):
        """
        Return the current preview widget.

        :rtype: QtWidgets.QWidget
        """
        return self._previewWidget

    def setPreviewWidget(self, widget):
        """
        Set the preview widget.

        :type widget: QtWidgets.QWidget
        :rtype: None
        """
        if self._previewWidget == widget:
            msg = 'Preview widget already contains widget "{0}"'
            msg.format(widget)
            logger.debug(msg)
        else:
            self.closePreviewWidget()
            self._previewWidget = widget
            if self._previewWidget:
                self._previewFrame.layout().addWidget(self._previewWidget)
                self._previewWidget.show()

    def closePreviewWidget(self):
        """
        Close and delete the preview widget.

        :rtype: None
        """
        if self._previewWidget:
            self._previewWidget.close()

        layout = self._previewFrame.layout()

        while layout.count():
            item = layout.takeAt(0)
            item.widget().hide()
            item.widget().close()
            item.widget().deleteLater()

        self._previewWidget = None

    # -----------------------------------------------------------------------
    # Support for saving and loading the widget state
    # -----------------------------------------------------------------------

    def settingsPath(self):
        """
        Return the settings path for the CatalogWidget

        :rtype: str
        """
        return self.SETTINGS_PATH

    def settings(self):
        """
        Return a dictionary with the widget settings.

        :rtype: dict
        """

        geometry = (
            self.geometry().x(),
            self.geometry().y(),
            self.geometry().width(),
            self.geometry().height()
        )

        settings = {}

        settings['dpi'] = self.dpi()
        settings['geometry'] = geometry
        settings['sizes'] = self._splitter.sizes()

        if self.theme():
            settings['theme'] = self.theme().settings()

        settings["recursiveSearch"] = self.isRecursiveSearchEnabled()

        settings["foldersWidgetVisible"] = self.isFoldersWidgetVisible()
        settings["previewWidgetVisible"] = self.isPreviewWidgetVisible()
        settings["menuBarWidgetVisible"] = self.isMenuBarWidgetVisible()
        settings["statusBarWidgetVisible"] = self.isStatusBarWidgetVisible()

        settings['searchWidget'] = self.searchWidget().settings()
        settings['foldersWidget'] = self.foldersWidget().settings()
        settings['itemsWidget'] = self.itemsWidget().settings()

        settings["path"] = self.path()

        return settings

    def setSettings(self, settings):
        """
        Set the widget settings from the given dictionary.

        :type settings: dict
        """
        themeSettings = settings.get("theme", None)
        if themeSettings:
            theme = studioqt.Theme()
            theme.setSettings(themeSettings)
            self.setTheme(theme)

        self.itemsWidget().setToastEnabled(False)

        path = settings.get("path")
        self.setRootPath(path)

        dpi = settings.get("dpi", 1.0)
        self.setDpi(dpi)

        sizes = settings.get('sizes', [140, 280, 180])
        if len(sizes) == 3:
            self.setSizes(sizes)

        x, y, width, height = settings.get("geometry", [200, 200, 860, 680])
        self.setGeometry(x, y, width, height)

        # Make sure the window is on the screen.
        screenGeometry = QtWidgets.QApplication.desktop().screenGeometry()
        screenWidth = screenGeometry.width()
        screenHeight = screenGeometry.height()

        if x < 0 or y < 0 or x > screenWidth or y > screenHeight:
            self.centerWindow()

        # Reload the stylesheet before loading the dock widget settings.
        # Otherwise the widget will show docked without a stylesheet.
        self.reloadStyleSheet()

        value = settings.get("foldersWidgetVisible", True)
        self.setFoldersWidgetVisible(value)

        value = settings.get("menuBarWidgetVisible", True)
        self.setMenuBarWidgetVisible(value)

        value = settings.get("previewWidgetVisible", True)
        self.setPreviewWidgetVisible(value)

        value = settings.get("statusBarWidgetVisible", True)
        self.setStatusBarWidgetVisible(value)

        searchWidgetSettings = settings.get('searchWidget', {})
        self.searchWidget().setSettings(searchWidgetSettings)

        foldersWidgetSettings = settings.get('foldersWidget', {})
        self.foldersWidget().setSettings(foldersWidgetSettings)

        itemsWidgetSettings = settings.get('itemsWidget', {})
        self.itemsWidget().setSettings(itemsWidgetSettings)

        self.itemsWidget().setToastEnabled(True)

        recursiveSearch = settings.get("recursiveSearch", self.RECURSIVE_SEARCH_ENABLED)
        self.setRecursiveSearchEnabled(recursiveSearch)

    def saveSettings(self):
        """
        Save the settings dictionary to a local json location.

        :rtype: None
        """
        settings = self.settings()

        path = self.settingsPath()
        key = self._name

        data = studiolibrary.readJson(path)
        data[key] = settings

        studiolibrary.saveJson(path, data)

    def loadSettings(self):
        """
        Read the settings dict from the local json location.

        :rtype: None
        """
        self.reloadStyleSheet()

        if self.database():
            settings = self.readSettings()
            self.setSettings(settings)

    def readSettings(self):
        """
        Read the settings data.

        :rtype: dict 
        """
        key = self.name()
        path = self.settingsPath()
        data = studiolibrary.readJson(path)
        return data.get(key, {})

    def isLoaded(self):
        """
        Return True if the Studio Library has been shown

        :rtype: bool
        """
        return self._isLoaded

    def setLoaded(self, loaded):
        """
        Set if the widget has been shown.

        :type loaded: bool
        :rtype: None 
        """
        self._isLoaded = loaded

    def setSizes(self, sizes):
        """
        :type sizes: (int, int, int)
        :rtype: None
        """
        fSize, cSize, pSize = sizes

        if pSize == 0:
            pSize = 200

        if fSize == 0:
            fSize = 120

        self._splitter.setSizes([fSize, cSize, pSize])
        self._splitter.setStretchFactor(1, 1)

    def centerWindow(self):
        """
        Center the widget to the center of the desktop.

        :rtype: None
        """
        geometry = self.frameGeometry()
        pos = QtWidgets.QApplication.desktop().cursor().pos()
        screen = QtWidgets.QApplication.desktop().screenNumber(pos)
        centerPoint = QtWidgets.QApplication.desktop().screenGeometry(
            screen).center()
        geometry.moveCenter(centerPoint)
        self.move(geometry.topLeft())

    # -----------------------------------------------------------------------
    # Overloading events
    # -----------------------------------------------------------------------

    def event(self, event):
        """
        :type event: QtWidgets.QEvent
        :rtype: QtWidgets.QEvent
        """
        if isinstance(event, QtGui.QKeyEvent):
            if studioqt.isControlModifier() and event.key() == QtCore.Qt.Key_F:
                self.searchWidget().setFocus()

        if isinstance(event, QtGui.QStatusTipEvent):
            self.statusWidget().setInfo(event.tip())

        return QtWidgets.QWidget.event(self, event)

    def keyReleaseEvent(self, event):
        """
        :type event: QtGui.QKeyEvent
        :rtype: None
        """
        for item in self.selectedItems():
            item.keyReleaseEvent(event)
        QtWidgets.QWidget.keyReleaseEvent(self, event)

    def closeEvent(self, event):
        """
        :type event: QtWidgets.QEvent
        :rtype: None
        """
        self.saveSettings()
        QtWidgets.QWidget.closeEvent(self, event)

    def show(self):
        """
        Overriding this method to always raise_ the widget on show.

        :rtype: None
        """
        QtWidgets.QWidget.show(self)
        self.setWindowState(QtCore.Qt.WindowNoState)
        self.raise_()

    def showEvent(self, event):
        """
        :type event: QtWidgets.QEvent
        :rtype: None
        """
        QtWidgets.QWidget.showEvent(self, event)
        if not self.isLoaded():
            self.setLoaded(True)
            self.loadSettings()

    # -----------------------------------------------------------------------
    # Support for themes and custom style sheets
    # -----------------------------------------------------------------------

    def dpi(self):
        """
        Return the current dpi for the library widget.

        :rtype: float
        """
        return float(self._dpi)

    def setDpi(self, dpi):
        """
        Set the current dpi for the library widget.

        :rtype: float
        """
        if not self.DPI_ENABLED:
            dpi = 1.0

        self._dpi = dpi

        self.itemsWidget().setDpi(dpi)
        self.menuBarWidget().setDpi(dpi)
        self.foldersWidget().setDpi(dpi)
        self.statusWidget().setFixedHeight(20 * dpi)

        self._splitter.setHandleWidth(2 * dpi)

        self.itemsWidget().setToast("DPI: {0}".format(int(dpi * 100)))

        self.reloadStyleSheet()

    def _dpiSliderChanged(self, value):
        """
        Triggered the dpi action changes value.

        :rtype: float
        """
        dpi = value / 100.0
        self.setDpi(dpi)

    def iconColor(self):
        """
        Return the icon color.

        :rtype: studioqt.Color
        """
        return self.theme().iconColor()

    def setTheme(self, theme):
        """
        Set the theme for the catalog widget.

        :type theme: studioqt.Theme 
        :rtype: None 
        """
        self._theme = theme
        self.reloadStyleSheet()

    def theme(self):
        """
        Return the current theme for the catalog widget.

        :rtype: studioqt.Theme 
        """
        return self._theme or studioqt.Theme()

    def reloadStyleSheet(self):
        """
        Reload the style sheet to the current theme.

        :rtype: None
        """
        theme = self.theme()
        theme.setDpi(self.dpi())

        options = theme.options()
        styleSheet = theme.styleSheet()

        color = studioqt.Color.fromString(options["ITEM_TEXT_COLOR"])
        self.itemsWidget().setTextColor(color)

        color = studioqt.Color.fromString(options["ITEM_TEXT_SELECTED_COLOR"])
        self.itemsWidget().setTextSelectedColor(color)

        color = studioqt.Color.fromString(options["ITEM_BACKGROUND_COLOR"])
        self.itemsWidget().setBackgroundColor(color)

        color = studioqt.Color.fromString(
            options["ITEM_BACKGROUND_HOVER_COLOR"])
        self.itemsWidget().setBackgroundHoverColor(color)

        color = studioqt.Color.fromString(
            options["ITEM_BACKGROUND_SELECTED_COLOR"])
        self.itemsWidget().setBackgroundSelectedColor(color)

        self.setStyleSheet(styleSheet)

        self.searchWidget().update()
        self.menuBarWidget().update()

    # -----------------------------------------------------------------------
    # Support for the Trash folder.
    # -----------------------------------------------------------------------

    def trashEnabled(self):
        return self._trashEnabled

    def setTrashEnabled(self, value):
        self._trashEnabled = value

    def trashPath(self):
        """
        :rtype: str
        """
        path = self.path()
        return u'{0}/{1}'.format(path, "Trash")

    def trashFolderExists(self):
        """
        :rtype: bool
        """
        return os.path.exists(self.trashPath())

    def createTrashFolder(self):
        """
        :rtype: None
        """
        path = self.trashPath()
        if not os.path.exists(path):
            os.makedirs(path)

    def isTrashFolderVisible(self):
        """
        :rtype: bool
        """
        return self._isTrashFolderVisible

    def setTrashFolderVisible(self, visible):
        """
        :type visible: str
        :rtype: None
        """
        self._isTrashFolderVisible = visible
        self.reloadFolders()

    def isTrashEnabled(self):
        """
        :rtype: bool
        """
        folders = self.selectedFolders()
        for folder in folders:
            if "Trash" in folder.path():
                return False

        items = self.selectedItems()
        for item in items:
            if "Trash" in item.path():
                return False

        return True

    def trashSelectedFoldersDialog(self):
        """
        :rtype: None
        """
        items = self.selectedFolders()

        if items:
            title = "Move selected folders to trash?"
            msg = "Are you sure you want to move the selected folder/s to the trash?"
            result = self.questionDialog(msg, title=title)

            if result == QtWidgets.QMessageBox.Yes:
                self.foldersWidget().clearSelection()
                self.trashItems(items)

    def trashSelectedItemsDialog(self):
        """
        Show the "move to trash" dialog for the selected items.

        :rtype: QtWidgets.QMessageBox.Button
        """
        items = self.selectedItems()

        return self.trashItemsDialog(
            items=items,
            title="Move selected items to trash?",
            message="Are you sure you want to move the selected item/s to the trash?",
        )

    def trashItemsDialog(self, items, title, message):
        """
        Show the "move to trash" dialog.

        :type items: list[studiolibrary.LibraryItem]
        :type title: str
        :type message: str

        :rtype: QtWidgets.QMessageBox.Button
        """
        result = None

        if items:
            title = title
            msg = message
            result = self.questionDialog(msg, title=title)

            if result == QtWidgets.QMessageBox.Yes:
                self.trashItems(items)

        return result

    def trashItems(self, items):
        """
        :items items: list[studiolibrary.LibraryItem]
        :rtype: None
        """
        trashPath = self.trashPath()

        self.createTrashFolder()

        try:
            for item in items:
                item.move(trashPath)

        except Exception, e:
            logger.exception(e.message)
            self.setError(e.message)
            raise

        finally:
            self.loadItems()

    # -----------------------------------------------------------------------
    # Support for message boxes
    # -----------------------------------------------------------------------

    def setInfo(self, text):
        self.statusWidget().setInfo(text)

    def setError(self, text):
        self.statusWidget().setError(unicode(text))
        self.setStatusBarWidgetVisible(True)

    def setWarning(self, text):
        self.statusWidget().setWarning(text)
        self.setStatusBarWidgetVisible(True)

    def setToast(self, text, duration=500):
        self.itemsWidget().setToast(text, duration)

    def criticalDialog(self, message, title="Error"):
        self.setError(message)
        return studioqt.MessageBox.critical(self, title, message)

    def questionDialog(self, message, title="Question"):
        buttons = QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel
        return studioqt.MessageBox.question(self, title, str(message), buttons)

    def updateWindowTitle(self):
        """
        Update the window title with the version and lock status.

        :rtype: None
        """
        title = "Studio Library - "
        title += studiolibrary.version() + " - " + self.name()

        if self.isLocked():
            title += " (Locked)"

        self.setWindowTitle(title)

    def setLoadedMessage(self, elapsedTime):
        """
        :type elapsedTime: time.time
        """
        itemCount = len(self._itemsWidget.items())
        hiddenCount = self.itemsHiddenCount()

        plural = ""
        if itemCount > 1:
            plural = "s"

        hiddenText = ""
        if hiddenCount > 0:

            hiddenPlural = ""
            if hiddenCount > 1:
                hiddenPlural = "s"

            hiddenText = "{0} item{1} hidden."
            hiddenText = hiddenText.format(hiddenCount, hiddenPlural)

        msg = "Displayed {0} item{1} in {2:.3f} seconds. {3}"
        msg = msg.format(itemCount, plural, elapsedTime, hiddenText)
        self.statusWidget().setInfo(msg)

    # -----------------------------------------------------------------------
    # Support for locking via regex
    # -----------------------------------------------------------------------

    def updateCreateItemButton(self):
        """
        Update the plus icon depending on if the library widget is locked.

        :rtype: None 
        """
        action = self.menuBarWidget().findAction("New Item")

        if self.isLocked():
            pixmap = studioqt.resource.pixmap("lock")
            action.setEnabled(False)
            action.setIcon(pixmap)
        else:
            pixmap = studioqt.resource.pixmap("add")
            action.setEnabled(True)
            action.setIcon(pixmap)

        self.menuBarWidget().update()

    def isLocked(self):
        """
        Return lock state of the library.

        :rtype: bool
        """
        return self._isLocked

    def setLocked(self, value):
        """
        Set the state of the widget to not editable.

        :type value: bool
        :rtype: None
        """
        self._isLocked = value

        self.foldersWidget().setLocked(value)
        self.itemsWidget().setLocked(value)

        self.updateCreateItemButton()
        self.updateWindowTitle()

        self.lockChanged.emit(value)

    def superusers(self):
        """
        Return the superusers for the widget. 

        :rtype: list[str] 
        """
        return self._superusers

    def setSuperusers(self, superusers):
        """
        Set the valid superusers for the library widget.

        This will lock all folders unless you're a superuser.

        :type superusers: list[str]
        :rtype: None
        """
        self._superusers = superusers
        self.updateLock()

    def lockRegExp(self):
        """
        Return the lock regexp used for locking the widget.

        :rtype: str
        """
        return self._lockRegExp

    def setLockRegExp(self, regExp):
        """
        Set the lock regexp used for locking the widget.

        Lock only folders that contain the given regExp in their path.

        :type regExp: str
        :rtype: None
        """
        self._lockRegExp = regExp
        self.updateLock()

    def unlockRegExp(self):
        """
        Return the unlock regexp used for unlocking the widget.

        :rtype: str
        """
        return self._unlockRegExp

    def setUnlockRegExp(self, regExp):
        """
        Return the unlock regexp used for locking the widget.

        Unlock only folders that contain the given regExp in their path.

        :type regExp: str
        :rtype: None
        """
        self._unlockRegExp = regExp
        self.updateLock()

    def isLockRegExpEnabled(self):
        """
        Return True if either the lockRegExp or unlockRegExp has been set.

        :rtype: bool
        """
        return not (
            self.superusers() is None
            and self.lockRegExp() is None
            and self.unlockRegExp() is None
        )

    def updateLock(self):
        """        
        Update the lock state for the library.

        This is triggered when the user clicks on a folder.

        :rtype: None
        """
        if not self.isLockRegExpEnabled():
            return

        superusers = self.superusers() or []
        reLocked = re.compile(self.lockRegExp() or "")
        reUnlocked = re.compile(self.unlockRegExp() or "")

        if studiolibrary.user() in superusers:
            self.setLocked(False)

        elif reLocked.match("") and reUnlocked.match(""):

            if superusers:
                # Lock if only the superusers arg is used
                self.setLocked(True)
            else:
                # Unlock if no keyword arguments are used
                self.setLocked(False)

        else:
            folders = self.selectedFolders()

            # Lock the selected folders that match the reLocked regx
            if not reLocked.match(""):
                for folder in folders:
                    if reLocked.search(folder.path()):
                        self.setLocked(True)
                        return

                self.setLocked(False)

            # Unlock the selected folders that match the reUnlocked regx
            if not reUnlocked.match(""):
                for folder in folders:
                    if reUnlocked.search(folder.path()):
                        self.setLocked(False)
                        return

                self.setLocked(True)

    # -----------------------------------------------------------------------
    # Misc
    # -----------------------------------------------------------------------

    def isCompactView(self):
        """
        Return True if both the folder and preview widget are hidden

        :rtype: bool
        """
        return not self.isFoldersWidgetVisible() and not self.isPreviewWidgetVisible()

    def toggleView(self):
        """
        Toggle the preview widget and folder widget visible.

        :rtype: None
        """
        compact = self.isCompactView()

        if studioqt.isControlModifier():
            compact = False
            self.setMenuBarWidgetVisible(compact)

        self.setPreviewWidgetVisible(compact)
        self.setFoldersWidgetVisible(compact)

    def updateViewButton(self):
        """
        Update/referesh the icon on the view button.

        :rtype: None
        """
        compact = self.isCompactView()
        action = self.menuBarWidget().findAction("View")

        if not compact:
            icon = studioqt.resource.icon("view_all")
        else:
            icon = studioqt.resource.icon("view_compact")

        action.setIcon(icon)

        self.menuBarWidget().update()

    def isRecursiveSearchEnabled(self):
        """
        Return True if recursive search is enabled.

        :rtype: bool
        """
        return self._recursiveSearchEnabled

    def setRecursiveSearchEnabled(self, value, loadItems=True):
        """
        Enable recursive search for searching sub folders.

        :type value: int
        :type loadItems: bool

        :rtype: None
        """
        self._recursiveSearchEnabled = value

        if loadItems:
            self.loadItems()

    @staticmethod
    def help():
        """
        :rtype: None
        """
        import webbrowser
        webbrowser.open(studiolibrary.HELP_URL)

    def setDebugMode(self, value):
        """
        :type value: bool
        """
        self._isDebug = value

        logger_ = logging.getLogger("studiolibrary")

        if value:
            logger_.setLevel(logging.DEBUG)
        else:
            logger_.setLevel(logging.INFO)

        self.debugModeChanged.emit(value)
        self.globalSignal.debugModeChanged.emit(self, value)

    def isDebug(self):
        """
        :rtype: bool
        """
        return self._isDebug

    def itemClasses(self):
        """
        Return ordered list of registred item classes.

        :rtype: list[studiolibrary.LibraryItem]
        """
        return []

    def findItemsInFolders(self, folders, depth=3, **kwargs):
        """
        Find and create new item instances by walking the given paths.

        :type folders: list[str]
        :type depth: int

        :rtype: collections.Iterable[studiolibrary.LibraryItem]
        """
        for folder in folders:
            for item in self.findItems(folder, depth=depth, **kwargs):
                yield item

    def itemsFromPaths(self, paths, **kwargs):
        """
        Return new item instances for the given paths.

        :type paths: list[str]:
        :rtype: collections.Iterable[studiolibrary.LibraryItem]
        """
        for path in paths:
            item = self.itemFromPath(path, **kwargs)
            if item:
                yield item

    def itemsFromUrls(self, urls, **kwargs):
        """
        Return new item instances for the given QUrl objects.

        :type urls: list[QtGui.QUrl]
        :rtype: list[studiolibrary.LibraryItem]
        """
        items = []
        for url in urls:
            path = url.toLocalFile()

            # Fixes a bug when dragging from windows explorer on windows 10
            if studiolibrary.isWindows():
                if path.startswith("/"):
                    path = path[1:]

            item = self.itemFromPath(path, **kwargs)

            if item:
                items.append(item)
            else:
                msg = 'Cannot find the item for path "{0}"'
                msg = msg.format(path)
                logger.warning(msg)

        return items

    def findItems(self, path, direction=studiolibrary.Direction.Down, depth=3, **kwargs):
        """
        Find and create new item instances by walking the given path.

        :type path: str
        :type direction: studiolibrary.Direction or str
        :type depth: int

        :rtype: collections.Iterable[studiolibrary.LibraryItem]
        """
        ignore = [
            ".studiolibrary",
            ".studioLibrary",
        ]

        paths = studiolibrary.findPaths(
            path,
            match=self.itemFromPath,
            ignore=ignore,
            direction=direction,
            depth=depth
        )

        return self.itemsFromPaths(paths, **kwargs)

    def itemFromPath(self, path, **kwargs):
        """
        Return a new item instance for the given path.

        :type path: str
        :rtype: studiolibrary.LibraryItem or None
        """
        for cls in self.itemClasses():
            if cls.isPathSuitable(path):
                return cls(path, **dict(kwargs, database=self.database, libraryWidget=self))

        return None


if __name__ == "__main__":

    with studioqt.app():

        path = u'C:/Users/Hovel/Dropbox/libraries/animation'
        widget = LibraryWidget.instance(path=path)
        widget.setLocked(True)
        widget.show()

        path = u'C:/Users/Hovel/Dropbox/libraries/animation/Character'
        widget = LibraryWidget.instance("Local", path=path)
        widget.show()
