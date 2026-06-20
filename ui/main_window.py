from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QStackedWidget, QFrame,
)
from PyQt6.QtCore import Qt, QByteArray
from core.state_manager import save_settings, load_settings
from .drive_selector_widget import DriveSelectorWidget
from .copy_mode_widget import CopyModeWidget
from .rename_mode_widget import RenameModeWidget
from .wipe_mode_widget import WipeModeWidget
from .help_dialog import HelpDialog
from .log_viewer_dialog import LogViewerDialog


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

        logs_btn = QPushButton("Logs")
        logs_btn.setFixedHeight(34)
        logs_btn.clicked.connect(self._show_logs)
        toolbar.addWidget(logs_btn)

        help_btn = QPushButton("Help")
        help_btn.setFixedHeight(34)
        help_btn.clicked.connect(self._show_help)
        toolbar.addWidget(help_btn)

        root.addLayout(toolbar)

        self._log_dialog = None

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

        # Reflect copy progress in the drive selector's status dots.
        self._copy_widget.copy_started.connect(self._drive_selector.mark_copy_pending)
        self._copy_widget.copy_result.connect(self._drive_selector.mark_copy_result)

        # Restore persisted window geometry and last-used mode.
        settings = load_settings()
        geo = settings.get("window_geometry")
        if geo:
            try:
                self.restoreGeometry(QByteArray.fromHex(geo.encode()))
            except Exception:
                pass
        active = settings.get("active_mode", 0)
        self._switch_mode(active if active in (0, 1, 2) else 0)

    def _switch_mode(self, index: int):
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._mode_buttons):
            btn.setChecked(i == index)
        save_settings({"active_mode": index})

    def _show_help(self):
        HelpDialog(parent=self).exec()

    def _show_logs(self):
        # Reuse a single non-modal viewer so repeated clicks just bring it
        # forward rather than stacking windows.
        if self._log_dialog is not None and self._log_dialog.isVisible():
            self._log_dialog.raise_()
            self._log_dialog.activateWindow()
            return
        self._log_dialog = LogViewerDialog(parent=self)
        self._log_dialog.show()

    def closeEvent(self, event):
        save_settings({"window_geometry": bytes(self.saveGeometry().toHex()).decode()})
        super().closeEvent(event)
