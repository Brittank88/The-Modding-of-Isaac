### PySide6 ###
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QMainWindow, QDockWidget, QTabWidget                  # Standard widgets.
from PySide6.QtGui import QIcon, QPixmap                                            # Standard GUI classes.
from PySide6.QtCore import Qt                                                       # Standard core classes.
from Widgets.Custom.QListWidgetPlaceholder import QListWidgetPlaceholder            # Custom PySide6 widgets.
from Resources import resources    # type: ignore                                   # Custom PySide6 assets.
from qt_material import apply_stylesheet                                            # Material theme.

class MainApp(QMainWindow):
    def __init__(self, parent=None, theme='dark_red.xml'):
        super().__init__(parent)

        ### OUTER WINDOW ###
        geometry = self.screen().availableGeometry()                    # Get available geometry dimensions.
        self.resize(geometry.width() * 0.75, geometry.height() * 0.75)  # Set window size based on geometry.
        self.setWindowTitle('TMoI Manager')                             # Set window title.
        self.setWindowIcon(QIcon(QPixmap(':/icons/AppIcon.png')))       # Set window icon.

        ### MOD LIST PAGE ###
        self.mod_list_page = QMainWindow(self)  # Create QMainMenu widget for page.

        ### MOD LIST DOCKABLES ###
        self.mod_list_page.mod_list_dockable = QDockWidget(self.mod_list_page)                              # Create dock widget.
        self.mod_list_page.mod_list_dockable.setWindowTitle('TMoI Mods List')                               # Set dock widget window title.
        self.mod_list_page.mod_list_dockable.setFloating(False)                                             # This is not a floating widget.

        self.mod_list_page.mod_list_dockable.mod_list = QListWidgetPlaceholder(                             # Create mods list widget.
            self.mod_list_page.mod_list_dockable,                                                           # Parent is the dockable widget.
            'It appears you have no mods!'                                                                  # Placeholder text when there are no mods.
        )
        self.mod_list_page.mod_list_dockable.mod_list.setDragDropMode(QAbstractItemView.InternalMove)       # Allow reordering of list items.
        self.mod_list_page.mod_list_dockable.setWidget(self.mod_list_page.mod_list_dockable.mod_list)       # Add list to dockable widget.
        self.mod_list_page.addDockWidget(Qt.LeftDockWidgetArea, self.mod_list_page.mod_list_dockable)       # Add dockable widget to page.

        self.mod_list_page.mod_list_dockable_2 = QDockWidget(self.mod_list_page)                            # Create dock widget.
        self.mod_list_page.mod_list_dockable_2.setWindowTitle('TMoI Mods List')                             # Set dock widget window title.
        self.mod_list_page.mod_list_dockable_2.setFloating(False)                                           # This is not a floating widget.

        self.mod_list_page.addDockWidget(Qt.RightDockWidgetArea, self.mod_list_page.mod_list_dockable_2)    # Add dock widget to page.

        ### TAB WIDGET ###
        self.main_tabs = QTabWidget(self)
        self.main_tabs.addTab(self.mod_list_page, 'Mods List')
        self.setCentralWidget(self.main_tabs)

        # Apply stylesheet.
        apply_stylesheet(self, theme)