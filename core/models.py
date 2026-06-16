from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DriveInfo:
    disk_id: str
    partition_id: str
    volume_name: str
    mount_point: str
    size_bytes: int
    filesystem: str

    COMPATIBLE_FILESYSTEMS = {"msdos", "ms-dos", "fat32", "fat16", "fat12", "exfat"}

    @property
    def is_mounted(self) -> bool:
        return bool(self.mount_point)

    @property
    def needs_format(self) -> bool:
        """True if the filesystem isn't one Tesla light show accepts (FAT/exFAT)."""
        fs = (self.filesystem or "").strip().lower()
        if not fs:
            return False
        return fs not in self.COMPATIBLE_FILESYSTEMS

    @property
    def display_size(self) -> str:
        gb = self.size_bytes / (1024 ** 3)
        if gb >= 1:
            return f"{gb:.1f} GB"
        mb = self.size_bytes / (1024 ** 2)
        return f"{mb:.0f} MB"


def _fmt_bytes(size: int) -> str:
    gb = size / (1024 ** 3)
    if gb >= 1:
        return f"{gb:.1f} GB"
    mb = size / (1024 ** 2)
    if mb >= 1:
        return f"{mb:.1f} MB"
    kb = size / 1024
    return f"{kb:.0f} KB"


@dataclass
class ShowFilePair:
    """A matched .fseq + audio (.mp3 or .wav) file pair."""
    fseq: Path
    audio: Path

    @property
    def stem(self) -> str:
        return self.fseq.stem

    @property
    def fseq_size(self) -> int:
        try:
            return self.fseq.stat().st_size
        except OSError:
            return 0

    @property
    def audio_size(self) -> int:
        try:
            return self.audio.stat().st_size
        except OSError:
            return 0

    @property
    def total_size_bytes(self) -> int:
        return self.fseq_size + self.audio_size

    @property
    def display_size(self) -> str:
        return _fmt_bytes(self.total_size_bytes)

    def is_valid(self) -> bool:
        """True only if both source files exist on disk."""
        return self.fseq.is_file() and self.audio.is_file()

    def missing_files(self) -> list[str]:
        """Return names of whichever files are missing."""
        missing = []
        if not self.fseq.is_file():
            missing.append(self.fseq.name)
        if not self.audio.is_file():
            missing.append(self.audio.name)
        return missing


@dataclass
class FileGroup:
    name: str
    files: list = field(default_factory=list)  # list[ShowFilePair]

    @property
    def total_size_bytes(self) -> int:
        return sum(p.total_size_bytes for p in self.files if p.is_valid())

    @property
    def display_size(self) -> str:
        return _fmt_bytes(self.total_size_bytes)


@dataclass
class CopyJob:
    groups: list
    drives: list
    erase_mode: str = "none"  # "none", "delete" (clear files only), "format" (full reformat)


@dataclass
class RenameJob:
    new_name: str
    drives: list


@dataclass
class WipeJob:
    drives: list
    new_name: str = "NO NAME"
