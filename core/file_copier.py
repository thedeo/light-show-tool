import logging
import shutil
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024  # 1 MB

# macOS recreates these on any mounted volume; they're permission-protected
# and aren't part of the light show, so leave them alone when clearing a drive.
SKIP_NAMES = {
    ".Spotlight-V100", ".fseventsd", ".Trashes", ".TemporaryItems",
    ".DocumentRevisions-V100", ".DS_Store",
}

# A freshly-surfaced volume can intermittently throw EIO while Spotlight is
# still indexing it (or under general Finder/diskarbitrationd lock
# contention with many drives mounted at once). Retry rather than failing
# the whole drive over what's usually a transient condition.
IO_RETRY_ATTEMPTS = 6
IO_RETRY_DELAY = 1.5  # seconds, multiplied by attempt number


def _with_io_retry(func, what: str):
    last_err = None
    for attempt in range(1, IO_RETRY_ATTEMPTS + 1):
        try:
            return func()
        except OSError as e:
            last_err = e
            logger.warning("%s failed (attempt %d/%d): %s", what, attempt, IO_RETRY_ATTEMPTS, e)
            time.sleep(IO_RETRY_DELAY * attempt)
    logger.error("%s failed after %d attempts: %s", what, IO_RETRY_ATTEMPTS, last_err)
    raise last_err


def _disable_spotlight(mount: Path) -> None:
    """Best-effort: stop Spotlight from indexing this volume so it can't
    hold a lock on directory reads while we're erasing/copying."""
    try:
        r = subprocess.run(
            ["mdutil", "-i", "off", str(mount)],
            capture_output=True, timeout=5,
        )
        logger.info(
            "mdutil -i off %s -> rc=%d %s",
            mount, r.returncode, r.stdout.decode(errors="replace").strip(),
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("Could not disable Spotlight indexing on %s: %s", mount, e)


def copy_groups_to_drive(groups, drive, erase_first, progress_callback, cancel_check):
    mount = Path(drive.mount_point)
    logger.info("Starting copy to %s (disk_id=%s, erase_first=%s)", mount, drive.disk_id, erase_first)

    # Last line of defense: never let an erase-contents pass run against
    # the root filesystem or an empty path, no matter where mount_point came from.
    if erase_first and (not drive.mount_point or mount.resolve() == Path("/")):
        logger.error("Refusing to erase %s — resolves to root or empty mount point", mount)
        raise RuntimeError(f"Refusing to erase contents of {mount} — not a real drive mount.")

    _disable_spotlight(mount)

    if erase_first:
        items = _with_io_retry(lambda: list(mount.iterdir()), f"Listing contents of {mount}")
        for item in items:
            if cancel_check():
                raise InterruptedError("Cancelled")
            if item.name in SKIP_NAMES:
                continue
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except OSError as e:
                logger.warning("Could not remove %s: %s", item, e)
                continue  # macOS-managed or permission-protected; leave it

    # Tesla requires all files in a root-level "LightShow" folder (case-sensitive)
    dest_dir = mount / "LightShow"
    _with_io_retry(lambda: dest_dir.mkdir(parents=True, exist_ok=True), f"Creating {dest_dir}")

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

    logger.info("%s: copying %d files (%d bytes total)", mount, len(file_list), total_bytes)

    bytes_done = 0
    for src_path, dest_path, size in file_list:
        if cancel_check():
            raise InterruptedError("Cancelled")

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        progress_callback(bytes_done, total_bytes, src_path.name)
        logger.debug("Copying %s -> %s (%d bytes)", src_path, dest_path, size)

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
            logger.error("Error copying %s to %s: %s", src_path, dest_path, e)
            raise RuntimeError(f"Error copying {src_path.name}: {e}") from e

    logger.info("Finished copying to %s", mount)
    progress_callback(total_bytes, total_bytes, "")
