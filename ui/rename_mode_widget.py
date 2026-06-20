from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox,
)
from PyQt6.QtCore import pyqtSlot
from core.models import RenameJob
from core.state_manager import save_settings, load_settings
from .confirm_dialog import ConfirmDialog
from .progress_dialog import ProgressDialog
from .workers import RenameWorker


class RenameModeWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_drives = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 8, 8)
        layout.setSpacing(12)

        title = QLabel("Rename Mode")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        desc = QLabel(
            "Rename all selected drives to the same label.\n"
            "FAT32 labels are limited to 11 characters and will be uppercased."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: gray;")
        layout.addWidget(desc)

        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("New label:"))
        self._name_edit = QLineEdit()
        self._name_edit.setMaxLength(11)
        self._name_edit.setPlaceholderText("e.g. SHOW2025")
        self._name_edit.setText(load_settings().get("rename_label", ""))
        self._name_edit.textChanged.connect(self._update_counter)
        self._name_edit.textChanged.connect(
            lambda text: save_settings({"rename_label": text})
        )
        name_layout.addWidget(self._name_edit)
        self._counter_label = QLabel(f"{len(self._name_edit.text())}/11")
        self._counter_label.setStyleSheet("color: gray; font-size: 11px;")
        name_layout.addWidget(self._counter_label)
        layout.addLayout(name_layout)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._rename_btn = QPushButton("Rename Selected Drives")
        self._rename_btn.setFixedHeight(32)
        self._rename_btn.clicked.connect(self._start_rename)
        btn_layout.addWidget(self._rename_btn)
        layout.addLayout(btn_layout)

    def _update_counter(self, text: str):
        self._counter_label.setText(f"{len(text)}/11")

    @pyqtSlot(list)
    def set_selected_drives(self, drives: list):
        self._selected_drives = drives

    def _start_rename(self):
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "No Name", "Enter a drive label.")
            return
        if not self._selected_drives:
            QMessageBox.warning(self, "No Drives", "Select at least one drive.")
            return

        job = RenameJob(new_name=name, drives=self._selected_drives)

        dlg = ConfirmDialog.for_rename(job)
        if dlg.exec() != ConfirmDialog.DialogCode.Accepted:
            return

        progress = ProgressDialog("Renaming Drives", parent=self)
        worker = RenameWorker(job, parent=self)

        worker.progress.connect(progress.update_progress)
        worker.drive_status.connect(
            lambda label, ok, err: progress.set_status(
                f"{'✓' if ok else '✗'} {label}" + (f": {err}" if err else "")
            )
        )
        worker.all_done.connect(progress.on_all_done)
        progress.rejected.connect(worker.cancel)

        worker.start()
        progress.exec()
        worker.wait()
