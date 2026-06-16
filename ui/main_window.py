from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QStackedWidget, QFrame,
)
from PyQt6.QtCore import Qt
from .drive_selector_widget import DriveSelectorWidget
from .copy_mode_widget import CopyModeWidget
from .rename_mode_widget import RenameModeWidget
from .wipe_mode_widget import WipeModeWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Light Show Tool")
        self.setMinimumSize(900, 600)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Mode toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        self._mode_buttons: list[QPushButton] = []
        for i, label in enumerate(["Copy", "Rename", "Wipe"]):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(34)
            btn.clicked.connect(lambda checked, idx=i: self._switch_mode(idx))
            toolbar.addWidget(btn)
            self._mode_buttons.append(btn)

        toolbar.addStretch()
        root.addLayout(toolbar)

        # Horizontal split: drive selector (left) + stacked modes (right)
        split = QHBoxLayout()
        split.setSpacing(8)

        self._drive_selector = DriveSelectorWidget()
        split.addWidget(self._drive_selector)

        # Vertical separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        split.addWidget(line)

        self._stack = QStackedWidget()
        self._copy_widget = CopyModeWidget()
        self._rename_widget = RenameModeWidget()
        self._wipe_widget = WipeModeWidget()
        self._stack.addWidget(self._copy_widget)
        self._stack.addWidget(self._rename_widget)
        self._stack.addWidget(self._wipe_widget)
        split.addWidget(self._stack, stretch=1)

        root.addLayout(split)

        # Connect drive selection to all mode widgets
        self._drive_selector.selection_changed.connect(self._copy_widget.set_selected_drives)
        self._drive_selector.selection_changed.connect(self._rename_widget.set_selected_drives)
        self._drive_selector.selection_changed.connect(self._wipe_widget.set_selected_drives)

        self._switch_mode(0)

    def _switch_mode(self, index: int):
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._mode_buttons):
            btn.setChecked(i == index)
