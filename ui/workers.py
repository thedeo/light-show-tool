import logging
import time
from PyQt6.QtCore import QThread, pyqtSignal
from core.drive_manager import (
    rename_drive, wipe_drive, refresh_drive_info, mount_drive, unmount_drive,
    iter_external_drives,
)
from core.file_copier import copy_groups_to_drive

logger = logging.getLogger(__name__)

# Pause between drives to let macOS/Finder settle each volume event
# before the next mount/unmount fires. Prevents Finder lock contention
# when operating on many drives simultaneously.
DRIVE_STAGGER_SECS = 1.5


def _stagger(index: int, total: int, cancelled_fn) -> bool:
    """Sleep between drives. Returns True if cancelled during sleep."""
    if index < total - 1:
        deadline = time.monotonic() + DRIVE_STAGGER_SECS
        while time.monotonic() < deadline:
            if cancelled_fn():
                return True
            time.sleep(0.1)
    return False


class DriveScanWorker(QThread):
    """Runs diskutil-based drive discovery off the main thread so a slow
    or wedged diskutil can never block the UI from appearing/responding.
    Emits each drive as soon as it's found so the UI can populate
    incrementally instead of waiting for the whole scan to finish."""
    drive_found = pyqtSignal(object)  # DriveInfo
    scan_done = pyqtSignal()

    def run(self):
        for drive in iter_external_drives():
            self.drive_found.emit(drive)
        self.scan_done.emit()


class CopyWorker(QThread):
    progress = pyqtSignal(int, int, str)         # bytes_done, bytes_total, filename (current drive)
    overall_progress = pyqtSignal(int, int, int) # percent, drives_completed, drives_total
    drive_status = pyqtSignal(str, bool, str)    # drive label, success, error
    all_done = pyqtSignal(bool, str)

    def __init__(self, job, parent=None):
        super().__init__(parent)
        self._job = job
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _attempt(self, drive, on_progress):
        """Run the copy (with optional erase) for one drive. Returns
        (success, error_message); error_message is "Cancelled" if the
        cancel flag was set mid-operation."""
        try:
            current_drive = drive
            delete_contents = False

            if self._job.erase_mode == "format":
                wipe_drive(drive, drive.volume_name)
                current_drive = refresh_drive_info(drive)
            elif self._job.erase_mode == "delete":
                delete_contents = True

            copy_groups_to_drive(
                self._job.groups,
                current_drive,
                delete_contents,
                on_progress,
                lambda: self._cancelled,
            )
            return True, ""
        except InterruptedError:
            return False, "Cancelled"
        except Exception as e:
            logger.exception("Operation failed for %s (%s)", drive.volume_name, drive.disk_id)
            return False, str(e)

    def run(self):
        errors = []
        total = len(self._job.drives)
        # Drives that fail are retried once at the end of the run, after
        # every other drive has finished — the recurring Errno 5 EIO seen
        # in practice is specific to whichever drive the app touches
        # first (likely racing a post-mount settling window for the whole
        # batch), and every later drive consistently proves the volume is
        # readable again within seconds.
        retry_queue = []

        for i, drive in enumerate(self._job.drives):
            if self._cancelled:
                break

            label = f"{drive.volume_name} ({drive.disk_id})"

            def on_progress(done, total_b, fname, _i=i):
                self.progress.emit(done, total_b, fname)
                frac = _i + (done / total_b if total_b else 0)
                self.overall_progress.emit(int(frac * 100 / total), _i, total)

            success, err = self._attempt(drive, on_progress)
            if success:
                self.drive_status.emit(label, True, "")
            elif err == "Cancelled":
                self.drive_status.emit(label, False, "Cancelled")
                break
            else:
                logger.warning("%s failed, deferring a retry to the end of the run: %s", label, err)
                retry_queue.append((drive, label))

            self.overall_progress.emit(int((i + 1) * 100 / total), i + 1, total)

            if _stagger(i, total, lambda: self._cancelled):
                break

        if retry_queue and not self._cancelled:
            self.progress.emit(0, 1, f"Retrying {len(retry_queue)} drive(s) that failed earlier...")
            for drive, label in retry_queue:
                if self._cancelled:
                    break

                def on_progress(done, total_b, fname):
                    self.progress.emit(done, total_b, fname)

                success, err = self._attempt(drive, on_progress)
                if success:
                    self.drive_status.emit(label, True, "(succeeded on retry)")
                elif err == "Cancelled":
                    self.drive_status.emit(label, False, "Cancelled")
                    break
                else:
                    errors.append(f"{label}: {err}")
                    self.drive_status.emit(label, False, err)

        if self._cancelled:
            self.all_done.emit(False, "Operation cancelled.")
        elif errors:
            self.all_done.emit(False, "\n".join(errors))
        else:
            self.all_done.emit(True, "")


class RenameWorker(QThread):
    progress = pyqtSignal(int, int, str)
    drive_status = pyqtSignal(str, bool, str)
    all_done = pyqtSignal(bool, str)

    def __init__(self, job, parent=None):
        super().__init__(parent)
        self._job = job
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        errors = []
        total = len(self._job.drives)
        for i, drive in enumerate(self._job.drives):
            if self._cancelled:
                break

            label = f"{drive.volume_name} ({drive.disk_id})"
            self.progress.emit(i, total, f"Renaming {label}...")
            try:
                rename_drive(drive, self._job.new_name)
                self.drive_status.emit(label, True, "")
            except Exception as e:
                logger.exception("Operation failed for %s", label)
                errors.append(f"{label}: {e}")
                self.drive_status.emit(label, False, str(e))

            if _stagger(i, total, lambda: self._cancelled):
                break

        if not self._cancelled:
            self.progress.emit(total, total, "")

        if self._cancelled:
            self.all_done.emit(False, "Operation cancelled.")
        elif errors:
            self.all_done.emit(False, "\n".join(errors))
        else:
            self.all_done.emit(True, "")


class MountActionWorker(QThread):
    progress = pyqtSignal(int, int, str)
    drive_status = pyqtSignal(str, bool, str)
    all_done = pyqtSignal(bool, str)

    def __init__(self, drives, mount: bool, parent=None):
        super().__init__(parent)
        self._drives = drives
        self._mount = mount
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        errors = []
        total = len(self._drives)
        verb = "Mounting" if self._mount else "Unmounting"
        action = mount_drive if self._mount else unmount_drive

        for i, drive in enumerate(self._drives):
            if self._cancelled:
                break

            label = f"{drive.volume_name} ({drive.disk_id})"
            self.progress.emit(i, total, f"{verb} {label}...")
            try:
                action(drive)
                self.drive_status.emit(label, True, "")
            except Exception as e:
                logger.exception("Operation failed for %s", label)
                errors.append(f"{label}: {e}")
                self.drive_status.emit(label, False, str(e))

            if _stagger(i, total, lambda: self._cancelled):
                break

        if not self._cancelled:
            self.progress.emit(total, total, "")

        if self._cancelled:
            self.all_done.emit(False, "Operation cancelled.")
        elif errors:
            self.all_done.emit(False, "\n".join(errors))
        else:
            self.all_done.emit(True, "")


class WipeWorker(QThread):
    progress = pyqtSignal(int, int, str)
    drive_status = pyqtSignal(str, bool, str)
    all_done = pyqtSignal(bool, str)

    def __init__(self, job, parent=None):
        super().__init__(parent)
        self._job = job
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        errors = []
        total = len(self._job.drives)
        for i, drive in enumerate(self._job.drives):
            if self._cancelled:
                break

            label = f"{drive.volume_name} ({drive.disk_id})"
            self.progress.emit(i, total, f"Wiping {label}...")
            try:
                wipe_drive(drive, self._job.new_name)
                self.drive_status.emit(label, True, "")
            except Exception as e:
                logger.exception("Operation failed for %s", label)
                errors.append(f"{label}: {e}")
                self.drive_status.emit(label, False, str(e))

            if _stagger(i, total, lambda: self._cancelled):
                break

        if not self._cancelled:
            self.progress.emit(total, total, "")

        if self._cancelled:
            self.all_done.emit(False, "Operation cancelled.")
        elif errors:
            self.all_done.emit(False, "\n".join(errors))
        else:
            self.all_done.emit(True, "")
