import logging
import shutil
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class SkipDrive(Exception):
    """Raised to abort the current drive's copy and move on to the next one,
    without cancelling the whole run (unlike InterruptedError)."""

# If the destination file size hasn't grown for this many seconds, the drive
# is considered stalled and the copy is aborted.  15 s is conservative — at
# even 0.1 MB/s a 1 MB chunk takes 10 s, so any genuine write stall shows up
# well within this window.
STALL_TIMEOUT = 15  # seconds

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
        proc = subprocess.Popen(
            ["mdutil", "-i", "off", str(mount)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            # Do NOT call proc.wait() here — with 16+ drives mounted, mdutil
            # can enter an uninterruptible kernel I/O wait (D state) where
            # SIGKILL has no effect. Waiting after kill would hang forever.
            logger.warning("mdutil -i off %s timed out, continuing without it", mount)
    except OSError as e:
        logger.warning("Could not disable Spotlight indexing on %s: %s", mount, e)


def copy_groups_to_drive(groups, drive, erase_first, progress_callback, cancel_check,
                         skip_check=None):
    if skip_check is None:
        skip_check = lambda: False

    def _check_interrupts():
        """Raise if the run was cancelled or the current drive was skipped."""
        if cancel_check():
            raise InterruptedError("Cancelled")
        if skip_check():
            raise SkipDrive("Skipped")

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
            _check_interrupts()
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
        _check_interrupts()

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        progress_callback(bytes_done, total_bytes, src_path.name)
        logger.debug("Copying %s -> %s (%d bytes)", src_path, dest_path, size)

        proc = subprocess.Popen(
            ["cp", str(src_path), str(dest_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        last_size = 0
        last_progress_t = time.monotonic()

        while True:
            try:
                proc.wait(timeout=0.25)
                break  # cp finished
            except subprocess.TimeoutExpired:
                pass  # still running — check stall and cancel below

            if cancel_check() or skip_check():
                proc.kill()
                _check_interrupts()

            # Track how many bytes cp has written so far so the progress bar
            # moves smoothly rather than jumping at file boundaries.
            try:
                current_size = dest_path.stat().st_size
            except OSError:
                current_size = last_size

            if current_size > last_size:
                last_size = current_size
                last_progress_t = time.monotonic()

            elapsed_stall = time.monotonic() - last_progress_t
            if elapsed_stall > STALL_TIMEOUT:
                proc.kill()
                logger.error(
                    "Drive stalled for %.0fs writing %s — aborting",
                    elapsed_stall, src_path.name,
                )
                raise RuntimeError(
                    f"Drive stalled for {elapsed_stall:.0f}s on {src_path.name} "
                    f"— it may be faulty or disconnected"
                )

            progress_callback(bytes_done + last_size, total_bytes, src_path.name)

        if proc.returncode != 0:
            logger.error("cp exited %d for %s", proc.returncode, src_path.name)
            raise RuntimeError(f"Failed to copy {src_path.name} (cp exit code {proc.returncode})")

        bytes_done += size
        progress_callback(bytes_done, total_bytes, src_path.name)

    logger.info("Finished copying to %s", mount)
    progress_callback(total_bytes, total_bytes, "")
