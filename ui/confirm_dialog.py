from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QCheckBox,
    QDialogButtonBox, QFrame,
)
from PyQt6.QtCore import Qt


class ConfirmDialog(QDialog):
    def __init__(self, summary_text: str, require_checkbox: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirm")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        label = QLabel(summary_text)
        label.setWordWrap(True)
        layout.addWidget(label)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)

        if require_checkbox:
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            layout.addWidget(line)
            self._checkbox = QCheckBox("I understand this is permanent and cannot be undone")
            self._checkbox.toggled.connect(self._ok_btn.setEnabled)
            layout.addWidget(self._checkbox)
            self._ok_btn.setEnabled(False)

        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    @staticmethod
    def for_copy(job) -> "ConfirmDialog":
        group_lines = "\n".join(
            f"  • {g.name} ({len(g.files)} file{'s' if len(g.files) != 1 else ''})"
            for g in job.groups
        )
        drive_lines = "\n".join(
            f"  • {d.volume_name} ({d.disk_id})" for d in job.drives
        )
        if job.erase_mode == "format":
            erase_note = "\n\nDrives will be FULLY REFORMATTED (FAT32) before copying."
        elif job.erase_mode == "delete":
            erase_note = "\n\nExisting files will be deleted before copying (format kept as-is)."
        else:
            erase_note = ""
        text = (
            f"Copy the following groups:\n{group_lines}\n\n"
            f"To {len(job.drives)} drive{'s' if len(job.drives) != 1 else ''}:\n{drive_lines}"
            f"{erase_note}"
        )
        return ConfirmDialog(text)

    @staticmethod
    def for_rename(job) -> "ConfirmDialog":
        drive_lines = "\n".join(
            f"  • {d.volume_name} ({d.disk_id})" for d in job.drives
        )
        text = (
            f"Rename {len(job.drives)} drive{'s' if len(job.drives) != 1 else ''} "
            f"to \"{job.new_name}\":\n{drive_lines}"
        )
        return ConfirmDialog(text)

    @staticmethod
    def for_wipe(job) -> "ConfirmDialog":
        drive_lines = "\n".join(
            f"  • {d.volume_name} ({d.disk_id})" for d in job.drives
        )
        text = (
            f"WIPE {len(job.drives)} drive{'s' if len(job.drives) != 1 else ''} "
            f"and format as FAT32 with label \"{job.new_name}\":\n{drive_lines}\n\n"
            "ALL DATA WILL BE PERMANENTLY DESTROYED."
        )
        return ConfirmDialog(text, require_checkbox=True)
