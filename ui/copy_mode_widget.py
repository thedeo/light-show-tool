from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton,
    QLabel, QMessageBox,
)
from PyQt6.QtCore import pyqtSlot
from core.models import CopyJob
from core.state_manager import save_state, load_state
from .file_group_widget import FileGroupPanelWidget
from .confirm_dialog import ConfirmDialog
from .progress_dialog import ProgressDialog
from .workers import CopyWorker


class CopyModeWidget(QWidget):
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

        # Bottom bar
        bottom = QHBoxLayout()
        bottom.addWidget(QLabel("Before copying:"))
        self._erase_combo = QComboBox()
        self._erase_combo.addItem("Don't erase", "none")
        self._erase_combo.addItem("Delete existing files (fast)", "delete")
        self._erase_combo.addItem("Format drive (slow, full reformat)", "format")
        bottom.addWidget(self._erase_combo)
        bottom.addStretch()
        self._copy_btn = QPushButton("Copy Groups to Selected Drives")
        self._copy_btn.setFixedHeight(32)
        self._copy_btn.clicked.connect(self._start_copy)
        bottom.addWidget(self._copy_btn)
        layout.addLayout(bottom)

        # Load persisted state before connecting signals so the initial
        # load doesn't trigger spurious saves.
        saved = load_state()
        if saved:
            self._panel.load_state_data(saved)

        self._panel.groups_changed.connect(self._update_copy_btn)
        self._panel.groups_changed.connect(self._save_state)
        self._update_copy_btn()

    @pyqtSlot(list)
    def set_selected_drives(self, drives: list):
        self._selected_drives = drives

    def _save_state(self):
        save_state(self._panel.get_state_data())

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
        )

        dlg = ConfirmDialog.for_copy(job)
        if dlg.exec() != ConfirmDialog.DialogCode.Accepted:
            return

        progress = ProgressDialog("Copying Files", parent=self)
        progress.enable_overall_progress(len(job.drives))
        worker = CopyWorker(job, parent=self)

        worker.progress.connect(progress.update_progress)
        worker.overall_progress.connect(progress.update_overall_progress)
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
