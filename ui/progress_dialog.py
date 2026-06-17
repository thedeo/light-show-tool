from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton,
    QHBoxLayout, QTextEdit, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSlot


class ProgressDialog(QDialog):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(480)
        self.setMinimumHeight(280)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        self._cancelled = False

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Overall progress across all drives — hidden unless a caller with
        # multiple drives opts in via enable_overall_progress().
        self._overall_label = QLabel("")
        self._overall_label.setStyleSheet("font-weight: bold;")
        self._overall_label.setVisible(False)
        layout.addWidget(self._overall_label)

        self._overall_bar = QProgressBar()
        self._overall_bar.setRange(0, 100)
        self._overall_bar.setVisible(False)
        layout.addWidget(self._overall_bar)

        self._overall_divider = QFrame()
        self._overall_divider.setFrameShape(QFrame.Shape.HLine)
        self._overall_divider.setVisible(False)
        layout.addWidget(self._overall_divider)

        self._status_label = QLabel("Preparing...")
        self._status_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._status_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        layout.addWidget(self._progress_bar)

        self._sub_label = QLabel("")
        self._sub_label.setStyleSheet("color: gray; font-size: 11px;")
        self._sub_label.setWordWrap(True)
        layout.addWidget(self._sub_label)

        # Scrollable log of completed drives
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(120)
        self._log.setStyleSheet("font-size: 11px; background: transparent; border: none;")
        layout.addWidget(self._log)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self._cancel_btn)
        layout.addLayout(btn_layout)

    def was_cancelled(self) -> bool:
        return self._cancelled

    def enable_overall_progress(self, total_drives: int):
        self._overall_label.setText(f"Overall: 0 of {total_drives} drives (0%)")
        self._overall_label.setVisible(True)
        self._overall_bar.setVisible(True)
        self._overall_divider.setVisible(True)

    @pyqtSlot(int, int, int)
    def update_overall_progress(self, percent: int, completed: int, total: int):
        self._overall_bar.setValue(percent)
        self._overall_label.setText(f"Overall: {completed} of {total} drives ({percent}%)")

    def _on_cancel(self):
        self._cancelled = True
        self._cancel_btn.setEnabled(False)
        self._status_label.setText("Cancelling...")

    @pyqtSlot(int, int, str)
    def update_progress(self, current: int, total: int, status: str):
        if total > 0:
            pct = int(current * 100 / total)
            self._progress_bar.setValue(pct)
        if status:
            self._sub_label.setText(status)

    def set_current_drive(self, label: str):
        self._status_label.setText(f"Copying {label}…")

    def set_status(self, text: str):
        # Completed drive results go only to the log, not the status label —
        # set_current_drive() owns the status label while work is in progress.
        if text:
            self._log.append(text)
            sb = self._log.verticalScrollBar()
            sb.setValue(sb.maximum())

    @pyqtSlot(bool, str)
    def on_all_done(self, success: bool, error_msg: str):
        self._cancel_btn.setEnabled(False)
        self._progress_bar.setValue(100)
        self._sub_label.setText("")
        if self._overall_bar.isVisible() and success:
            self._overall_bar.setValue(100)

        if success:
            self._status_label.setText("All done!")
        else:
            self._status_label.setText("Finished with errors." if not self._cancelled else "Cancelled.")
            if error_msg:
                self._log.append(f"\n{error_msg}")

        # Re-enable close and switch button to Close
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
        self.show()
        self._cancel_btn.setText("Close")
        self._cancel_btn.setEnabled(True)
        self._cancel_btn.clicked.disconnect()
        self._cancel_btn.clicked.connect(self.accept)
