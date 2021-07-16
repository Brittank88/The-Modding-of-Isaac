import sys
from PySide6.QtWidgets import QApplication
from TMoI_Widgets import MainApp

def setup_app():

    # Create the app.
    app = QApplication(sys.argv)

    # Instantiate and show the main app GUI.
    app_widget = MainApp()
    app_widget.show()

    # Ensure that the app is deleted when we close it.
    app.aboutToQuit.connect(app.deleteLater)

    # Run and exit when app is finished executing.
    sys.exit(app.exec())

def main():
    
    # Setup GUI app.
    setup_app()

if __name__ == '__main__': main()