import re
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QCheckBox, QFrame, QSizePolicy, QMessageBox, QProgressBar,
    QApplication,
)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from .progress_dialog import ProgressDialog
from .workers import (
    MountActionWorker, DriveScanWorker, DrivePollWorker, DriveResolveWorker,
)

# How often to poll for drives being plugged in or pulled. The poll itself is
# a single read-only `diskutil list` run off the main thread, and is skipped
# entirely while any operation is in progress (see _poll_for_changes), so this
# can be relaxed without affecting responsiveness during copies.
POLL_INTERVAL_MS = 5000


def _disk_sort_key(disk_id: str) -> int:
    """Numeric order for disk identifiers so disk4 sorts before disk10
    (a plain string sort would put disk10 first)."""
    m = re.search(r"(\d+)$", disk_id or "")
    return int(m.group(1)) if m else 0


class DriveRow(QWidget):
    toggled = pyqtSignal(object, bool)  # DriveInfo, checked

    # Status-dot colors, by copy lifecycle state.
    _DOT_BLUE = "#1565c0"    # loaded, not yet copied this session
    _DOT_GREEN = "#2e7d32"   # copied successfully
    _DOT_ORANGE = "#ef6c00"  # copy failed
    _DOT_RED = "#c62828"     # unmounted — can't be copied

    def __init__(self, drive, parent=None):
        super().__init__(parent)
        self.drive = drive
        self._copy_status = "pending"  # "pending" | "success" | "failed"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        self._checkbox = QCheckBox()
        self._checkbox.setChecked(False)
        self._checkbox.setEnabled(drive.is_mounted)
        if not drive.is_mounted:
            self._checkbox.setToolTip("Drive is unmounted — mount it before selecting it.")
        self._checkbox.toggled.connect(lambda checked: self.toggled.emit(self.drive, checked))
        layout.addWidget(self._checkbox)

        self._status_label = QLabel("●")
        self._status_label.setFixedWidth(14)
        layout.addWidget(self._status_label)
        self._update_status_dot()

        name_text = Path(drive.mount_point).name if drive.is_mounted else drive.volume_name
        name_style = "color: gray;" if not drive.is_mounted else ""
        tooltip_lines = []
        if drive.needs_format:
            name_text = f"{name_text} ⚠"
            name_style = "color: #c66400; font-weight: bold;"
            tooltip_lines.append(
                f"Format: {drive.filesystem or 'unknown'} — not Tesla-compatible "
                "(needs FAT32/exFAT). Use Wipe Mode to reformat."
            )

        name_label = QLabel(name_text)
        name_label.setMinimumWidth(100)
        if name_style:
            name_label.setStyleSheet(name_style)
        if tooltip_lines:
            name_label.setToolTip("\n".join(tooltip_lines))
        layout.addWidget(name_label)

        disk_label = QLabel(drive.disk_id)
        disk_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(disk_label)

        layout.addStretch()

        size_label = QLabel(drive.display_size)
        size_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(size_label)

    def set_checked(self, checked: bool):
        self._checkbox.setChecked(checked)

    def is_checked(self) -> bool:
        return self._checkbox.isChecked()

    def set_copy_status(self, status: str):
        """status: 'pending', 'success', or 'failed'."""
        self._copy_status = status
        self._update_status_dot()

    def _update_status_dot(self):
        # A copy result takes priority over mount state so a drive that was
        # auto-ejected after a successful copy still reads as green.
        if self._copy_status == "success":
            color, tip = self._DOT_GREEN, "Copied successfully"
        elif self._copy_status == "failed":
            color, tip = self._DOT_ORANGE, "Copy failed"
        elif self.drive.is_mounted:
            color, tip = self._DOT_BLUE, "Mounted — not yet copied"
        else:
            color, tip = self._DOT_RED, "Unmounted"
        self._status_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        self._status_label.setToolTip(tip)


class DriveSelectorWidget(QWidget):
    selection_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(240)
        self.setMaximumWidth(320)

        self._drives = []
        self._rows: list[DriveRow] = []
        self._scan_worker = None
        self._poll_worker = None
        self._resolve_worker = None
        # Checked disk_ids carried across a refresh so an auto-refresh (or a
        # manual one) doesn't wipe the user's selection.
        self._preserve_checked: set[str] = set()
        self._action_buttons: list[QPushButton] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._header = QLabel("Drives")
        self._header.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(self._header)

        # Banner shown for the full duration of a scan — kept separate from
        # the drive list so it stays visible even after drives start
        # appearing incrementally, not just while the list is empty.
        self._scan_banner = QFrame()
        self._scan_banner.setStyleSheet(
            "background-color: #2d5a78; border-radius: 4px;"
        )
        banner_layout = QHBoxLayout(self._scan_banner)
        banner_layout.setContentsMargins(8, 6, 8, 6)
        banner_layout.setSpacing(6)

        self._scan_spinner = QProgressBar()
        self._scan_spinner.setRange(0, 0)  # indeterminate
        self._scan_spinner.setFixedWidth(40)
        self._scan_spinner.setFixedHeight(10)
        self._scan_spinner.setTextVisible(False)
        self._scan_spinner.setStyleSheet(
            "QProgressBar { background-color: rgba(255, 255, 255, 40); "
            "border: none; border-radius: 5px; }"
            "QProgressBar::chunk { background-color: #4a90d9; border-radius: 5px; }"
        )
        banner_layout.addWidget(self._scan_spinner)

        scan_label = QLabel("Scanning for drives…")
        scan_label.setStyleSheet("color: white; font-weight: bold; font-size: 11px;")
        banner_layout.addWidget(scan_label)
        banner_layout.addStretch()

        self._scan_banner.setVisible(False)
        layout.addWidget(self._scan_banner)

        # Scroll area for drive rows
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch()
        self._scroll.setWidget(self._list_container)
        layout.addWidget(self._scroll)

        # Buttons
        btn_layout = QHBoxLayout()
        select_all_btn = QPushButton("All")
        select_all_btn.setFixedHeight(26)
        select_all_btn.clicked.connect(self._select_all)
        btn_layout.addWidget(select_all_btn)
        self._action_buttons.append(select_all_btn)

        deselect_all_btn = QPushButton("None")
        deselect_all_btn.setFixedHeight(26)
        deselect_all_btn.clicked.connect(self._deselect_all)
        btn_layout.addWidget(deselect_all_btn)
        self._action_buttons.append(deselect_all_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedHeight(26)
        refresh_btn.clicked.connect(self.refresh)
        btn_layout.addWidget(refresh_btn)
        self._action_buttons.append(refresh_btn)

        layout.addLayout(btn_layout)

        mount_btn_layout = QHBoxLayout()
        mount_all_btn = QPushButton("Mount All")
        mount_all_btn.setFixedHeight(26)
        mount_all_btn.clicked.connect(self._mount_all)
        mount_btn_layout.addWidget(mount_all_btn)
        self._action_buttons.append(mount_all_btn)

        unmount_all_btn = QPushButton("Unmount All")
        unmount_all_btn.setFixedHeight(26)
        unmount_all_btn.clicked.connect(self._unmount_all)
        mount_btn_layout.addWidget(unmount_all_btn)
        self._action_buttons.append(unmount_all_btn)

        layout.addLayout(mount_btn_layout)

        self._no_drives_label = QLabel("No external drives detected.")
        self._no_drives_label.setStyleSheet("color: gray; font-size: 11px;")
        self._no_drives_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.refresh()

        # Poll for hot-plugged / removed drives and refresh only when the set
        # of attached disks actually changes.
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll_for_changes)
        self._poll_timer.start()

    def _busy(self) -> bool:
        """True if any drive work or modal operation is in progress — in which
        case background polling must hold off."""
        return (
            self._scan_worker is not None
            or self._poll_worker is not None
            or self._resolve_worker is not None
            or QApplication.activeModalWidget() is not None
        )

    def _poll_for_changes(self):
        # Never poll while a scan/poll/resolve is running, or while any
        # operation/dialog is open — copies, wipes, renames and mounts all run
        # behind an application-modal dialog, and we must not disturb the
        # drives (or rebuild the list) mid-operation.
        if self._busy():
            return

        self._poll_worker = DrivePollWorker(parent=self)
        self._poll_worker.polled.connect(self._on_polled)
        self._poll_worker.start()

    def _on_polled(self, disk_ids):
        self._poll_worker = None
        if disk_ids is None:
            return  # diskutil hiccup — leave the list as-is, try again next tick
        # Re-check guards: an operation may have started while we polled.
        if self._scan_worker is not None or self._resolve_worker is not None:
            return
        if QApplication.activeModalWidget() is not None:
            return

        current = {d.disk_id for d in self._drives}
        removed = current - disk_ids
        added = disk_ids - current

        # Incrementally update rather than rebuilding the whole list — no
        # "Scanning…" flicker, and existing selections stay put. A full scan
        # only happens at launch or on a manual Refresh.
        if removed:
            self._remove_drives(removed)
        if added:
            self._resolve_added(added)

    def _remove_drives(self, disk_ids):
        for row in [r for r in self._rows if r.drive.disk_id in disk_ids]:
            row.setParent(None)
            self._rows.remove(row)
        self._drives = [d for d in self._drives if d.disk_id not in disk_ids]
        self._show_no_drives_if_empty()
        self._update_header()
        self._emit_selection()

    def _resolve_added(self, disk_ids):
        # The "No external drives detected." placeholder must go before rows
        # are appended; _on_drive_found inserts ahead of the trailing stretch.
        if self._no_drives_label.parent() is not None:
            self._no_drives_label.setParent(None)
        self._resolve_worker = DriveResolveWorker(disk_ids, parent=self)
        self._resolve_worker.drive_found.connect(self._on_drive_found)
        self._resolve_worker.done.connect(self._on_resolve_done)
        self._resolve_worker.start()

    def _on_resolve_done(self):
        self._resolve_worker = None

    def _show_no_drives_if_empty(self):
        if self._drives:
            return
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._list_layout.addWidget(self._no_drives_label)
        self._list_layout.addStretch()

    def refresh(self):
        if self._scan_worker is not None:
            return  # a scan is already in flight

        # A full scan supersedes any in-flight incremental resolve — drop it so
        # its drive_found emissions don't double-add rows during the rebuild.
        if self._resolve_worker is not None:
            try:
                self._resolve_worker.drive_found.disconnect(self._on_drive_found)
                self._resolve_worker.done.disconnect(self._on_resolve_done)
            except TypeError:
                pass
            self._resolve_worker = None

        # Remember which drives were selected so the rebuild below doesn't
        # silently drop the user's selection (matters most for auto-refresh).
        self._preserve_checked = {
            row.drive.disk_id for row in self._rows if row.is_checked()
        }

        # Clear existing rows and show a placeholder immediately — never
        # block the UI thread waiting on diskutil, which can wedge.
        for row in self._rows:
            row.setParent(None)
        self._rows.clear()
        self._drives = []

        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        self._list_layout.addStretch()
        self._scan_banner.setVisible(True)
        self._update_header()

        for btn in self._action_buttons:
            btn.setEnabled(False)

        self._scan_worker = DriveScanWorker(parent=self)
        self._scan_worker.drive_found.connect(self._on_drive_found)
        self._scan_worker.scan_done.connect(self._on_scan_done)
        self._scan_worker.start()

    def _on_drive_found(self, drive):
        row = DriveRow(drive)
        row.toggled.connect(self._on_row_toggled)
        # Restore a prior selection (only mounted drives can be checked).
        if drive.is_mounted and drive.disk_id in self._preserve_checked:
            row.set_checked(True)

        # Keep the list in natural disk order so an incrementally-added drive
        # lands in its proper place, not at the bottom. (The full scan already
        # arrives sorted, so this leaves that path's ordering unchanged.) The
        # row's layout index matches its index in _rows — the only extra item
        # in the layout is the trailing stretch.
        pos = len(self._drives)
        key = _disk_sort_key(drive.disk_id)
        for i, d in enumerate(self._drives):
            if _disk_sort_key(d.disk_id) > key:
                pos = i
                break

        self._drives.insert(pos, drive)
        self._rows.insert(pos, row)
        self._list_layout.insertWidget(pos, row)

        self._update_header()
        self._emit_selection()

    def _update_header(self):
        total = len(self._drives)
        if not total:
            self._header.setText("Drives")
            return
        selected = sum(1 for row in self._rows if row.is_checked())
        self._header.setText(f"Drives ({selected} of {total} selected)")

    def mark_copy_pending(self, disk_ids: list):
        """Reset the given drives' status dots to blue at the start of a run."""
        targets = set(disk_ids)
        for row in self._rows:
            if row.drive.disk_id in targets:
                row.set_copy_status("pending")

    def mark_copy_result(self, disk_id: str, success: bool):
        for row in self._rows:
            if row.drive.disk_id == disk_id:
                row.set_copy_status("success" if success else "failed")
                break

    def _on_scan_done(self):
        self._scan_worker = None
        self._scan_banner.setVisible(False)
        for btn in self._action_buttons:
            btn.setEnabled(True)

        if not self._drives:
            while self._list_layout.count():
                item = self._list_layout.takeAt(0)
                if item.widget():
                    item.widget().setParent(None)
            self._list_layout.addWidget(self._no_drives_label)
            self._list_layout.addStretch()

        self._emit_selection()

    def _on_row_toggled(self, drive, checked):
        self._emit_selection()

    def _emit_selection(self):
        selected = [
            row.drive for row in self._rows if row.is_checked()
        ]
        self._update_header()
        self.selection_changed.emit(selected)

    def _select_all(self):
        for row in self._rows:
            if row.drive.is_mounted:
                row.set_checked(True)
        self._emit_selection()

    def _deselect_all(self):
        for row in self._rows:
            row.set_checked(False)
        self._emit_selection()

    def selected_drives(self) -> list:
        return [row.drive for row in self._rows if row.is_checked()]

    def _mount_all(self):
        targets = [d for d in self._drives if not d.is_mounted]
        if not targets:
            QMessageBox.information(self, "Mount All", "All drives are already mounted.")
            return
        self._run_mount_action(targets, mount=True)

    def _unmount_all(self):
        targets = [d for d in self._drives if d.is_mounted]
        if not targets:
            QMessageBox.information(self, "Unmount All", "All drives are already unmounted.")
            return
        confirm = QMessageBox.question(
            self,
            "Unmount All Drives",
            f"Unmount {len(targets)} mounted drive(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._run_mount_action(targets, mount=False)

    def _run_mount_action(self, drives: list, mount: bool):
        verb = "Mounting" if mount else "Unmounting"
        progress = ProgressDialog(f"{verb} Drives", parent=self)
        worker = MountActionWorker(drives, mount, parent=self)

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

        self.refresh()
