from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton,
    QHBoxLayout, QTextEdit,
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

        self._status_label = QLabel("Starting...")
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

    def set_status(self, text: str):
        self._status_label.setText(text)
        # Append completed drive results to the log
        if text:
            self._log.append(text)
            # Scroll to bottom
            sb = self._log.verticalScrollBar()
            sb.setValue(sb.maximum())

    @pyqtSlot(bool, str)
    def on_all_done(self, success: bool, error_msg: str):
        self._cancel_btn.setEnabled(False)
        self._progress_bar.setValue(100)
        self._sub_label.setText("")

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
