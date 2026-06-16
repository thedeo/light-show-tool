from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox,
    QListWidget, QListWidgetItem, QInputDialog, QScrollArea,
    QFrame, QAbstractItemView, QDialog, QMessageBox, QGridLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QFont
from core.models import FileGroup, ShowFilePair

AUDIO_EXTS = {".mp3", ".wav"}


def _fmt_bytes(size: int) -> str:
    gb = size / (1024 ** 3)
    if gb >= 1:
        return f"{gb:.2f} GB"
    mb = size / (1024 ** 2)
    if mb >= 1:
        return f"{mb:.2f} MB"
    kb = size / 1024
    return f"{kb:.0f} KB"


def _find_pair(path: Path):
    ext = path.suffix.lower()
    stem = path.stem
    directory = path.parent

    if ext == ".fseq":
        for aext in AUDIO_EXTS:
            candidate = directory / (stem + aext)
            if candidate.is_file():
                return path, candidate
        return None
    elif ext in AUDIO_EXTS:
        candidate = directory / (stem + ".fseq")
        if candidate.is_file():
            return candidate, path
        return None
    else:
        return None


def _is_show_ext(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTS | {".fseq"}


# ---------------------------------------------------------------------------
# Info dialog
# ---------------------------------------------------------------------------

class ShowPairInfoDialog(QDialog):
    def __init__(self, pair: ShowFilePair, parent=None):
        super().__init__(parent)
        self.setWindowTitle(pair.stem)
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel(pair.stem)
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        if not pair.is_valid():
            warn = QLabel(
                "\u26a0\ufe0f  One or more source files are missing:\n"
                + "\n".join(f"  \u2022 {f}" for f in pair.missing_files())
            )
            warn.setStyleSheet("color: #cc6600; font-size: 11px;")
            warn.setWordWrap(True)
            layout.addWidget(warn)

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setSpacing(6)

        def _file_label(path: Path) -> str:
            exists = path.is_file()
            return str(path) if exists else f"{path}  [NOT FOUND]"

        rows = [
            ("Sequence file", _file_label(pair.fseq)),
            ("Sequence size", _fmt_bytes(pair.fseq_size)),
            ("Audio file", _file_label(pair.audio)),
            ("Audio size", _fmt_bytes(pair.audio_size)),
            ("Combined size", pair.display_size),
            ("Directory", str(pair.fseq.parent)),
        ]
        for r, (label, value) in enumerate(rows):
            lbl = QLabel(label + ":")
            lbl.setStyleSheet("color: gray; font-size: 11px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            val = QLabel(value)
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            if "NOT FOUND" in value:
                val.setStyleSheet("color: #cc0000;")
            grid.addWidget(lbl, r, 0)
            grid.addWidget(val, r, 1)

        layout.addLayout(grid)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)


# ---------------------------------------------------------------------------
# Per-pair row widget
# ---------------------------------------------------------------------------

class ShowPairRowWidget(QWidget):
    remove_requested = pyqtSignal()

    def __init__(self, pair: ShowFilePair, parent=None):
        super().__init__(parent)
        self._pair = pair
        valid = pair.is_valid()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(4)

        name_label = QLabel(pair.stem)
        if not valid:
            # Strikethrough + muted colour to signal the files are gone
            font = name_label.font()
            font.setStrikeOut(True)
            name_label.setFont(font)
            name_label.setStyleSheet("color: #999999;")
            missing = ", ".join(pair.missing_files())
            name_label.setToolTip(f"Missing: {missing}")
        else:
            name_label.setToolTip(f"{pair.fseq.name}\n{pair.audio.name}")
        layout.addWidget(name_label, stretch=1)

        if not valid:
            warn_label = QLabel("\u26a0")
            warn_label.setStyleSheet("color: #cc6600; font-size: 12px;")
            warn_label.setToolTip("Source files not found — this pair will be skipped on copy")
            layout.addWidget(warn_label)
        else:
            size_label = QLabel(pair.display_size)
            size_label.setStyleSheet("color: gray; font-size: 10px;")
            layout.addWidget(size_label)

        info_btn = QPushButton("\u24d8")
        info_btn.setFixedSize(22, 22)
        info_btn.setStyleSheet("border: none; font-size: 13px; color: #4a90d9;")
        info_btn.setToolTip("Show file details")
        info_btn.clicked.connect(self._show_info)
        layout.addWidget(info_btn)

        remove_btn = QPushButton("\u2715")
        remove_btn.setFixedSize(22, 22)
        remove_btn.setStyleSheet("border: none; color: red; font-weight: bold;")
        remove_btn.setToolTip("Remove")
        remove_btn.clicked.connect(self.remove_requested)
        layout.addWidget(remove_btn)

    def _show_info(self):
        ShowPairInfoDialog(self._pair, self).exec()


# ---------------------------------------------------------------------------
# Drop area
# ---------------------------------------------------------------------------

class FileDropArea(QListWidget):
    pairs_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stems: set[str] = set()

        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setMinimumHeight(80)
        self.setMaximumHeight(200)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        if not event.mimeData().hasUrls():
            event.ignore()
            return

        missing_pairs: list[str] = []
        added = 0
        seen_this_drop: set[str] = set()

        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if not path.is_file() or not _is_show_ext(path):
                continue

            stem = path.stem
            if stem in self._stems or stem in seen_this_drop:
                continue
            seen_this_drop.add(stem)

            result = _find_pair(path)
            if result is None:
                missing_ext = ".fseq" if path.suffix.lower() in AUDIO_EXTS else ".mp3/.wav"
                missing_pairs.append(f'"{path.name}" - could not find matching {missing_ext}')
            else:
                self._add_pair(ShowFilePair(fseq=result[0], audio=result[1]))
                added += 1

        event.acceptProposedAction()

        if missing_pairs:
            QMessageBox.warning(
                self,
                "Missing Paired File",
                "The following files could not be paired:\n\n"
                + "\n".join(f"  \u2022 {m}" for m in missing_pairs)
                + "\n\nMake sure the .fseq and audio files share the same base name "
                "and are in the same folder.",
            )

        if added:
            self.pairs_changed.emit()

    def load_pairs(self, pairs: list) -> None:
        """Populate from saved state. Missing files are shown greyed out."""
        for pair in pairs:
            self._add_pair(pair)
        if pairs:
            self.pairs_changed.emit()

    def _add_pair(self, pair: ShowFilePair):
        self._stems.add(pair.stem)

        item = QListWidgetItem()
        item.setSizeHint(QSize(0, 34))
        item.setData(Qt.ItemDataRole.UserRole, pair)

        row_widget = ShowPairRowWidget(pair)
        row_widget.remove_requested.connect(lambda item=item: self._remove_item(item))

        self.addItem(item)
        self.setItemWidget(item, row_widget)

    def _remove_item(self, item: QListWidgetItem):
        pair: ShowFilePair = item.data(Qt.ItemDataRole.UserRole)
        self._stems.discard(pair.stem)
        self.takeItem(self.row(item))
        self.pairs_changed.emit()

    def get_pairs(self) -> list:
        return [
            self.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.count())
        ]

    def get_valid_pairs(self) -> list:
        return [p for p in self.get_pairs() if p.is_valid()]

    def get_invalid_pairs(self) -> list:
        return [p for p in self.get_pairs() if not p.is_valid()]


# ---------------------------------------------------------------------------
# Card
# ---------------------------------------------------------------------------

class FileGroupCard(QWidget):
    removed = pyqtSignal(object)
    changed = pyqtSignal()

    def __init__(self, group: FileGroup, parent=None):
        super().__init__(parent)
        self.group = group

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 6)

        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(8, 6, 8, 6)
        frame_layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)

        self._checkbox = QCheckBox()
        self._checkbox.setChecked(True)
        self._checkbox.setToolTip("Include this group in the copy operation")
        self._checkbox.toggled.connect(self._on_selection_toggled)
        header.addWidget(self._checkbox)

        self._name_label = QLabel(group.name)
        self._name_label.setStyleSheet("font-weight: bold;")
        header.addWidget(self._name_label)
        header.addStretch()

        self._size_label = QLabel("0 KB")
        self._size_label.setStyleSheet("color: gray; font-size: 11px;")
        header.addWidget(self._size_label)

        remove_btn = QPushButton("\u2715")
        remove_btn.setFixedSize(22, 22)
        remove_btn.setStyleSheet("color: red; font-weight: bold; border: none;")
        remove_btn.setToolTip("Delete this group")
        remove_btn.clicked.connect(lambda: self.removed.emit(self))
        header.addWidget(remove_btn)

        frame_layout.addLayout(header)

        self._drop_area = FileDropArea()
        self._drop_area.pairs_changed.connect(self._on_pairs_changed)
        frame_layout.addWidget(self._drop_area)

        drop_hint = QLabel("Drag .fseq or audio files here — pairs detected automatically")
        drop_hint.setStyleSheet("color: gray; font-size: 10px;")
        drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(drop_hint)

        outer.addWidget(frame)
        self._update_visual_state()

    def _on_pairs_changed(self):
        self.group.files = self._drop_area.get_pairs()
        self._size_label.setText(self.group.display_size)
        self.changed.emit()

    def _on_selection_toggled(self):
        self._update_visual_state()
        self.changed.emit()

    def _update_visual_state(self):
        checked = self._checkbox.isChecked()
        self._drop_area.setEnabled(checked)
        self._name_label.setStyleSheet(
            "font-weight: bold;" if checked else "font-weight: bold; color: gray;"
        )

    def is_selected(self) -> bool:
        return self._checkbox.isChecked()

    def set_selected(self, value: bool):
        self._checkbox.setChecked(value)

    def get_group(self) -> FileGroup:
        self.group.files = self._drop_area.get_pairs()
        return self.group

    def get_invalid_pairs(self) -> list:
        return self._drop_area.get_invalid_pairs()


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

class FileGroupPanelWidget(QWidget):
    groups_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: list[FileGroupCard] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        toolbar = QHBoxLayout()
        lbl = QLabel("Groups")
        lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
        toolbar.addWidget(lbl)
        toolbar.addStretch()

        all_btn = QPushButton("All")
        all_btn.setFixedHeight(24)
        all_btn.clicked.connect(self._select_all)
        toolbar.addWidget(all_btn)

        none_btn = QPushButton("None")
        none_btn.setFixedHeight(24)
        none_btn.clicked.connect(self._deselect_all)
        toolbar.addWidget(none_btn)

        layout.addLayout(toolbar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.setSpacing(0)
        self._container_layout.addStretch()
        scroll.setWidget(self._container)
        layout.addWidget(scroll)

        add_btn = QPushButton("+ New Group")
        add_btn.clicked.connect(self._add_group)
        layout.addWidget(add_btn)

    # ------------------------------------------------------------------
    def _create_card(self, group: FileGroup, selected: bool = True) -> FileGroupCard:
        card = FileGroupCard(group)
        card.set_selected(selected)
        card.removed.connect(self._remove_card)
        card.changed.connect(self.groups_changed)
        idx = self._container_layout.count() - 1
        self._container_layout.insertWidget(idx, card)
        self._cards.append(card)
        return card

    def _add_group(self):
        name, ok = QInputDialog.getText(self, "New Group", "Group name:")
        if ok and name.strip():
            self._create_card(FileGroup(name=name.strip()))
            self.groups_changed.emit()

    def _remove_card(self, card: FileGroupCard):
        self._container_layout.removeWidget(card)
        card.setParent(None)
        self._cards.remove(card)
        self.groups_changed.emit()

    def _select_all(self):
        for card in self._cards:
            card.set_selected(True)
        self.groups_changed.emit()

    def _deselect_all(self):
        for card in self._cards:
            card.set_selected(False)
        self.groups_changed.emit()

    # ------------------------------------------------------------------
    def get_groups(self) -> list:
        return [card.get_group() for card in self._cards]

    def get_selected_groups(self) -> list:
        result = []
        for card in self._cards:
            if card.is_selected():
                g = card.get_group()
                if g.files:
                    result.append(g)
        return result

    def total_group_count(self) -> int:
        return len(self._cards)

    def collect_invalid_pairs(self) -> list[tuple[str, list]]:
        """Return [(group_name, [ShowFilePair, ...]), ...] for missing pairs."""
        result = []
        for card in self._cards:
            if card.is_selected():
                invalid = card.get_invalid_pairs()
                if invalid:
                    result.append((card.group.name, invalid))
        return result

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def get_state_data(self) -> list:
        result = []
        for card in self._cards:
            g = card.get_group()
            result.append({
                "name": g.name,
                "selected": card.is_selected(),
                "pairs": [
                    {"fseq": str(p.fseq), "audio": str(p.audio)}
                    for p in g.files
                ],
            })
        return result

    def load_state_data(self, state_data: list) -> None:
        for entry in state_data:
            group = FileGroup(name=entry.get("name", "Group"))
            card = self._create_card(group, selected=entry.get("selected", True))

            pairs = []
            for p in entry.get("pairs", []):
                fseq = Path(p.get("fseq", ""))
                audio = Path(p.get("audio", ""))
                # Include even if files are missing — shown greyed out in UI
                if fseq.name and audio.name:
                    pairs.append(ShowFilePair(fseq=fseq, audio=audio))

            if pairs:
                card._drop_area.load_pairs(pairs)
