from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QCheckBox, QFrame, QSizePolicy,
)
from PyQt6.QtCore import pyqtSignal, Qt
from core.drive_manager import list_external_drives


class DriveRow(QWidget):
    toggled = pyqtSignal(object, bool)  # DriveInfo, checked

    def __init__(self, drive, parent=None):
        super().__init__(parent)
        self.drive = drive

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        self._checkbox = QCheckBox()
        self._checkbox.setChecked(False)
        self._checkbox.toggled.connect(lambda checked: self.toggled.emit(self.drive, checked))
        layout.addWidget(self._checkbox)

        name_label = QLabel(drive.volume_name)
        name_label.setMinimumWidth(100)
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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QLabel("Drives")
        header.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(header)

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

        deselect_all_btn = QPushButton("None")
        deselect_all_btn.setFixedHeight(26)
        deselect_all_btn.clicked.connect(self._deselect_all)
        btn_layout.addWidget(deselect_all_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedHeight(26)
        refresh_btn.clicked.connect(self.refresh)
        btn_layout.addWidget(refresh_btn)

        layout.addLayout(btn_layout)

        self._no_drives_label = QLabel("No external drives detected.")
        self._no_drives_label.setStyleSheet("color: gray; font-size: 11px;")
        self._no_drives_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.refresh()

    def refresh(self):
        # Clear existing rows
        for row in self._rows:
            row.setParent(None)
        self._rows.clear()

        # Remove stretch
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        self._drives = list_external_drives()

        if not self._drives:
            self._list_layout.addWidget(self._no_drives_label)
        else:
            for drive in self._drives:
                row = DriveRow(drive)
                row.toggled.connect(self._on_row_toggled)
                self._rows.append(row)
                self._list_layout.addWidget(row)

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
            row.set_checked(True)
        self._emit_selection()

    def _deselect_all(self):
        for row in self._rows:
            row.set_checked(False)
        self._emit_selection()

    def selected_drives(self) -> list:
        return [row.drive for row in self._rows if row.is_checked()]
