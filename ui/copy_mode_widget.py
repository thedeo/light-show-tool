from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton,
    QLabel, QMessageBox, QCheckBox,
)
from PyQt6.QtCore import pyqtSlot, pyqtSignal
from core.models import CopyJob
from core.state_manager import save_state, load_state, save_settings, load_settings
from .file_group_widget import FileGroupPanelWidget
from .confirm_dialog import ConfirmDialog
from .progress_dialog import ProgressDialog
from .workers import CopyWorker


class CopyModeWidget(QWidget):
    # Forwarded to the drive selector so its status dots reflect copy results.
    copy_started = pyqtSignal(list)       # disk_ids about to be copied
    copy_result = pyqtSignal(str, bool)   # disk_id, success

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_drives = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("Copy Mode")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        self._panel = FileGroupPanelWidget()
        layout.addWidget(self._panel)

        # Options row: how to prepare each drive before copying.
        options = QHBoxLayout()
        options.addWidget(QLabel("Before copying:"))
        self._erase_combo = QComboBox()
        self._erase_combo.addItem("Don't erase", "none")
        self._erase_combo.addItem("Delete existing files (fast)", "delete")
        self._erase_combo.addItem("Format drive (slow, full reformat)", "format")
        options.addWidget(self._erase_combo)
        options.addStretch()
        self._unmount_check = QCheckBox("Eject when done")
        self._unmount_check.setToolTip(
            "Unmount each drive as soon as its copy finishes, so it's safe to pull."
        )
        options.addWidget(self._unmount_check)
        layout.addLayout(options)

        # Primary action on its own full-width row for prominence.
        self._copy_btn = QPushButton("Copy Groups to Selected Drives")
        self._copy_btn.setFixedHeight(38)
        self._copy_btn.clicked.connect(self._start_copy)
        layout.addWidget(self._copy_btn)

        # Load persisted state before connecting signals so the initial
        # load doesn't trigger spurious saves.
        saved = load_state()
        if saved:
            self._panel.load_state_data(saved)

        settings = load_settings()
        idx = self._erase_combo.findData(settings.get("erase_mode", "none"))
        if idx >= 0:
            self._erase_combo.setCurrentIndex(idx)
        self._unmount_check.setChecked(bool(settings.get("eject_when_done", False)))

        self._panel.groups_changed.connect(self._update_copy_btn)
        self._panel.groups_changed.connect(self._save_state)
        self._erase_combo.currentIndexChanged.connect(self._save_settings)
        self._unmount_check.toggled.connect(self._save_settings)
        self._update_copy_btn()

    @pyqtSlot(list)
    def set_selected_drives(self, drives: list):
        self._selected_drives = drives

    def _save_state(self):
        save_state(self._panel.get_state_data())

    def _save_settings(self):
        save_settings({
            "erase_mode": self._erase_combo.currentData(),
            "eject_when_done": self._unmount_check.isChecked(),
        })

    def _update_copy_btn(self):
        n_sel = len(self._panel.get_selected_groups())
        n_total = self._panel.total_group_count()

        if n_total == 0:
            self._copy_btn.setText("Copy Groups to Selected Drives")
        elif n_sel == 0:
            self._copy_btn.setText("No Groups Selected")
        elif n_sel == n_total:
            self._copy_btn.setText(
                f"Copy All {n_total} Group{'s' if n_total != 1 else ''} to Selected Drives"
            )
        else:
            self._copy_btn.setText(
                f"Copy {n_sel} of {n_total} Groups to Selected Drives"
            )

    def _start_copy(self):
        groups = self._panel.get_selected_groups()
        if not groups:
            QMessageBox.warning(
                self,
                "No Groups Selected",
                "Check at least one group that contains files.",
            )
            return
        if not self._selected_drives:
            QMessageBox.warning(self, "No Drives", "Select at least one drive.")
            return

        erase_mode = self._erase_combo.currentData()

        # Drives in a non-Tesla-compatible format won't be fixed by deleting
        # files alone — only "format" reformats the filesystem.
        if erase_mode != "format":
            bad_drives = [d for d in self._selected_drives if d.needs_format]
            if bad_drives:
                names = "\n".join(
                    f"  • {d.volume_name} ({d.disk_id}) — {d.filesystem or 'unknown'}"
                    for d in bad_drives
                )
                proceed = QMessageBox.warning(
                    self,
                    "Incompatible Drive Format",
                    f"These drives aren't in a Tesla-compatible format "
                    f"(FAT32/exFAT):\n\n{names}\n\n"
                    "Choose \"Format drive\" above, or wipe them first. "
                    "Continue anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                )
                if proceed != QMessageBox.StandardButton.Yes:
                    return

        # Warn about any missing source files before proceeding
        invalid = self._panel.collect_invalid_pairs()
        if invalid:
            lines = []
            skipped_count = 0
            for group_name, pairs in invalid:
                for p in pairs:
                    lines.append(f"  \u2022 [{group_name}] {p.stem}")
                    skipped_count += 1
            proceed = QMessageBox.warning(
                self,
                "Missing Source Files",
                f"{skipped_count} show file pair{'s' if skipped_count != 1 else ''} "
                "cannot be copied because the source files were moved or deleted:\n\n"
                + "\n".join(lines)
                + "\n\nThese will be skipped. Continue with the remaining files?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if proceed != QMessageBox.StandardButton.Yes:
                return

            # Strip invalid pairs from the groups before building the job
            for group in groups:
                group.files = [p for p in group.files if p.is_valid()]
            groups = [g for g in groups if g.files]

            if not groups:
                QMessageBox.information(
                    self,
                    "Nothing to Copy",
                    "All selected groups have missing source files. Nothing was copied.",
                )
                return

        job = CopyJob(
            groups=groups,
            drives=self._selected_drives,
            erase_mode=erase_mode,
            unmount_when_done=self._unmount_check.isChecked(),
        )

        dlg = ConfirmDialog.for_copy(job)
        if dlg.exec() != ConfirmDialog.DialogCode.Accepted:
            return

        progress = ProgressDialog("Copying Files", parent=self)
        progress.enable_overall_progress(len(job.drives))
        progress.enable_skip()
        worker = CopyWorker(job, parent=self)

        # Reset the selector's dots to "pending" (blue) for this run's drives.
        self.copy_started.emit([d.disk_id for d in job.drives])

        def on_drive_status(disk_id, label, ok, err):
            progress.set_status(
                f"{'✓' if ok else '✗'} {label}" + (f": {err}" if err else "")
            )
            # Green on success, orange on a genuine failure. Skipped/cancelled
            # drives weren't really copied, so leave their dot blue (pending).
            if ok:
                self.copy_result.emit(disk_id, True)
            elif err not in ("Cancelled", "Skipped"):
                self.copy_result.emit(disk_id, False)

        worker.progress.connect(progress.update_progress)
        worker.overall_progress.connect(progress.update_overall_progress)
        worker.drive_starting.connect(progress.set_current_drive)
        worker.drive_status.connect(on_drive_status)
        worker.all_done.connect(progress.on_all_done)
        progress.rejected.connect(worker.cancel)
        progress.skip_requested.connect(worker.skip_current)

        worker.start()
        progress.exec()
        worker.wait()
