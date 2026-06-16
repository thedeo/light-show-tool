import shutil
import time
from pathlib import Path

CHUNK_SIZE = 1024 * 1024  # 1 MB

# macOS recreates these on any mounted volume; they're permission-protected
# and aren't part of the light show, so leave them alone when clearing a drive.
SKIP_NAMES = {
    ".Spotlight-V100", ".fseventsd", ".Trashes", ".TemporaryItems",
    ".DocumentRevisions-V100", ".DS_Store",
}

# A volume can briefly throw EIO right after it's mounted (still settling),
# especially with many drives mounted at once. Retry the first touch rather
# than failing the whole drive over a transient hiccup.
IO_RETRY_ATTEMPTS = 4
IO_RETRY_DELAY = 0.75  # seconds, multiplied by attempt number


def _with_io_retry(func):
    last_err = None
    for attempt in range(IO_RETRY_ATTEMPTS):
        try:
            return func()
        except OSError as e:
            last_err = e
            time.sleep(IO_RETRY_DELAY * (attempt + 1))
    raise last_err


def copy_groups_to_drive(groups, drive, erase_first, progress_callback, cancel_check):
    mount = Path(drive.mount_point)

    if erase_first:
        for item in _with_io_retry(lambda: list(mount.iterdir())):
            if cancel_check():
                raise InterruptedError("Cancelled")
            if item.name in SKIP_NAMES:
                continue
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except OSError:
                continue  # macOS-managed or permission-protected; leave it

    # Tesla requires all files in a root-level "LightShow" folder (case-sensitive)
    dest_dir = mount / "LightShow"
    _with_io_retry(lambda: dest_dir.mkdir(parents=True, exist_ok=True))

    # Build flat list of (src, dest, size) from ShowFilePair items
    total_bytes = 0
    file_list = []
    for group in groups:
        for pair in group.files:
            for src_path in (pair.fseq, pair.audio):
                try:
                    size = src_path.stat().st_size
                except OSError:
                    size = 0
                total_bytes += size
                file_list.append((src_path, dest_dir / src_path.name, size))

    bytes_done = 0
    for src_path, dest_path, size in file_list:
        if cancel_check():
            raise InterruptedError("Cancelled")

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        progress_callback(bytes_done, total_bytes, src_path.name)

        try:
            with open(src_path, "rb") as fsrc, open(dest_path, "wb") as fdst:
                while True:
                    if cancel_check():
                        raise InterruptedError("Cancelled")
                    chunk = fsrc.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    fdst.write(chunk)
                    bytes_done += len(chunk)
                    progress_callback(bytes_done, total_bytes, src_path.name)
        except InterruptedError:
            raise
        except OSError as e:
            raise RuntimeError(f"Error copying {src_path.name}: {e}") from e

    progress_callback(total_bytes, total_bytes, "")
