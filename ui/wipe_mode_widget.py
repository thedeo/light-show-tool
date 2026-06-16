from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox,
)
from PyQt6.QtCore import pyqtSlot
from core.models import WipeJob
from .confirm_dialog import ConfirmDialog
from .progress_dialog import ProgressDialog
from .workers import WipeWorker


class WipeModeWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_drives = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 8, 8)
        layout.setSpacing(12)

        title = QLabel("Wipe Mode")
        title.setStyleSheet("font-weight: bold; font-size: 14px; color: red;")
        layout.addWidget(title)

        warning = QLabel(
            "WARNING: This will permanently erase ALL data on the selected drives\n"
            "and reformat them as FAT32. This cannot be undone."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "color: white; background-color: #cc0000; padding: 8px; border-radius: 4px;"
        )
        layout.addWidget(warning)

        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Volume label after wipe:"))
        self._name_edit = QLineEdit("NO NAME")
        self._name_edit.setMaxLength(11)
        self._name_edit.textChanged.connect(self._update_counter)
        name_layout.addWidget(self._name_edit)
        self._counter_label = QLabel("7/11")
        self._counter_label.setStyleSheet("color: gray; font-size: 11px;")
        name_layout.addWidget(self._counter_label)
        layout.addLayout(name_layout)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._wipe_btn = QPushButton("Wipe Selected Drives")
        self._wipe_btn.setFixedHeight(32)
        self._wipe_btn.setStyleSheet(
            "QPushButton { background-color: #cc0000; color: white; font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #aa0000; }"
            "QPushButton:pressed { background-color: #880000; }"
        )
        self._wipe_btn.clicked.connect(self._start_wipe)
        btn_layout.addWidget(self._wipe_btn)
        layout.addLayout(btn_layout)

    def _update_counter(self, text: str):
        self._counter_label.setText(f"{len(text)}/11")

    @pyqtSlot(list)
    def set_selected_drives(self, drives: list):
        self._selected_drives = drives

    def _start_wipe(self):
        new_name = self._name_edit.text().strip() or "NO NAME"
        if not self._selected_drives:
            QMessageBox.warning(self, "No Drives", "Select at least one drive.")
            return

        job = WipeJob(drives=self._selected_drives, new_name=new_name)

        dlg = ConfirmDialog.for_wipe(job)
        if dlg.exec() != ConfirmDialog.DialogCode.Accepted:
            return

        progress = ProgressDialog("Wiping Drives", parent=self)
        worker = WipeWorker(job, parent=self)

        worker.progress.connect(
            lambda done, total, status: progress.update_progress(done, total, status)
        )
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
