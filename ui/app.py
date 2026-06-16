import sys
from PyQt6.QtWidgets import QApplication
from .main_window import MainWindow


def run():
    app = QApplication(sys.argv)
    app.setApplicationName("LightShowTool")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
