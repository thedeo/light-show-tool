from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QCheckBox, QFrame, QSizePolicy, QMessageBox, QProgressBar,
)
from PyQt6.QtCore import pyqtSignal, Qt
from .progress_dialog import ProgressDialog
from .workers import MountActionWorker, DriveScanWorker


class DriveRow(QWidget):
    toggled = pyqtSignal(object, bool)  # DriveInfo, checked

    def __init__(self, drive, parent=None):
        super().__init__(parent)
        self.drive = drive

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        self._checkbox = QCheckBox()
        self._checkbox.setChecked(False)
        self._checkbox.setEnabled(drive.is_mounted)
        if not drive.is_mounted:
            self._checkbox.setToolTip("Drive is unmounted — mount it before selecting it.")
        self._checkbox.toggled.connect(lambda checked: self.toggled.emit(self.drive, checked))
        layout.addWidget(self._checkbox)

        status_label = QLabel("●")
        status_label.setFixedWidth(14)
        if drive.is_mounted:
            status_label.setStyleSheet("color: #2e7d32; font-size: 12px;")
            status_label.setToolTip("Mounted")
        else:
            status_label.setStyleSheet("color: #c62828; font-size: 12px;")
            status_label.setToolTip("Unmounted")
        layout.addWidget(status_label)

        name_text = drive.volume_name
        name_style = "color: gray;" if not drive.is_mounted else ""
        tooltip_lines = []
        if drive.needs_format:
            name_text = f"{drive.volume_name} ⚠"
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


class DriveSelectorWidget(QWidget):
    selection_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(240)
        self.setMaximumWidth(320)

        self._drives = []
        self._rows: list[DriveRow] = []
        self._scan_worker = None
        self._action_buttons: list[QPushButton] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QLabel("Drives")
        header.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(header)

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

    def refresh(self):
        if self._scan_worker is not None:
            return  # a scan is already in flight

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

        for btn in self._action_buttons:
            btn.setEnabled(False)

        self._scan_worker = DriveScanWorker(parent=self)
        self._scan_worker.drive_found.connect(self._on_drive_found)
        self._scan_worker.scan_done.connect(self._on_scan_done)
        self._scan_worker.start()

    def _on_drive_found(self, drive):
        self._drives.append(drive)

        row = DriveRow(drive)
        row.toggled.connect(self._on_row_toggled)
        self._rows.append(row)
        # Insert above the trailing stretch so new rows append in order.
        self._list_layout.insertWidget(self._list_layout.count() - 1, row)

        self._emit_selection()

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
