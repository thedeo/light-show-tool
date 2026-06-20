from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton,
    QLabel, QCheckBox,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QTextCursor, QFontDatabase
from core.logging_setup import LOG_PATH

POLL_INTERVAL_MS = 1000


class LogViewerDialog(QDialog):
    """A live, tailing view of the run log. Non-modal so it can stay open and
    keep updating while a copy/wipe/rename runs behind its modal dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Logs")
        self.setMinimumSize(680, 460)
        # Stay a normal window, not modal — let the user watch while working.
        self.setModal(False)

        self._read_pos = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        path_label = QLabel(str(LOG_PATH))
        path_label.setStyleSheet("color: gray; font-size: 11px;")
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(path_label)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        layout.addWidget(self._text)

        controls = QHBoxLayout()
        self._autoscroll = QCheckBox("Auto-scroll")
        self._autoscroll.setChecked(True)
        controls.addWidget(self._autoscroll)
        controls.addStretch()
        clear_btn = QPushButton("Clear view")
        clear_btn.setToolTip("Clear the view (does not modify the log file)")
        clear_btn.clicked.connect(self._text.clear)
        controls.addWidget(clear_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        controls.addWidget(close_btn)
        layout.addLayout(controls)

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)

        self._poll()  # show current contents immediately
        self._timer.start()

    def _poll(self):
        try:
            size = LOG_PATH.stat().st_size
        except OSError:
            return  # log not written yet, or briefly unavailable

        # A new app run truncates the log; if it shrank, start over.
        if size < self._read_pos:
            self._read_pos = 0
            self._text.clear()

        try:
            with open(LOG_PATH, "r", errors="replace") as f:
                f.seek(self._read_pos)
                new_text = f.read()
                self._read_pos = f.tell()
        except OSError:
            return

        if not new_text:
            return

        sb = self._text.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4

        self._text.moveCursor(QTextCursor.MoveOperation.End)
        self._text.insertPlainText(new_text)

        if self._autoscroll.isChecked() and at_bottom:
            sb.setValue(sb.maximum())

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
