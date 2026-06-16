import logging
import subprocess
import time
import plistlib
from .models import DriveInfo

logger = logging.getLogger(__name__)

# diskutil calls are normally near-instant, but can wedge under heavy
# Finder/diskarbitrationd lock contention (seen with 16+ simultaneously
# mounted drives). Every call is timeout-bounded so a stuck diskutil can
# never hang the app indefinitely.
INFO_TIMEOUT = 5
ACTION_TIMEOUT = 20
ERASE_TIMEOUT = 180

# Enumerating every external disk takes longer than a single-disk info
# query, and gets slower still under the same load that causes the I/O
# retries elsewhere in this app — give it more time and a couple retries
# rather than reporting zero drives on one slow response.
LIST_TIMEOUT = 15
LIST_RETRY_ATTEMPTS = 3


def _diskutil(args: list, timeout: float):
    """Run diskutil, returning CompletedProcess or None on timeout."""
    try:
        r = subprocess.run(
            ["diskutil", *args],
            capture_output=True,
            timeout=timeout,
        )
        if r.returncode != 0:
            logger.warning(
                "diskutil %s -> rc=%d stderr=%s",
                " ".join(args), r.returncode, r.stderr.decode(errors="replace").strip(),
            )
        return r
    except subprocess.TimeoutExpired:
        logger.error("diskutil %s timed out after %ss", " ".join(args), timeout)
        return None


def _require(r, action: str) -> None:
    if r is None:
        raise TimeoutError(f"{action} timed out — diskutil did not respond.")
    if r.returncode != 0:
        msg = r.stderr.decode(errors="replace").strip()
        raise RuntimeError(msg or f"{action} failed.")


def _boot_disk_id():
    """Whole-disk identifier the Mac is currently running from.

    diskutil's "external" filter already excludes internal disks, but a
    Mac can also boot from an external drive (common with Thunderbolt/USB
    boot volumes) — that disk would otherwise show up as a normal external
    drive here and become eligible for Wipe/erase. Always exclude it.
    """
    r = _diskutil(["info", "-plist", "/"], INFO_TIMEOUT)
    if r is None or r.returncode != 0:
        return None
    info = plistlib.loads(r.stdout)
    return info.get("ParentWholeDisk") or info.get("DeviceIdentifier")


def iter_external_drives():
    """Yield each external, non-boot drive as soon as it's resolved, rather
    than waiting for every disk to be queried — the per-disk diskutil calls
    are the slow part, so callers can show drives as they're found."""
    result = None
    for attempt in range(1, LIST_RETRY_ATTEMPTS + 1):
        result = _diskutil(["list", "-plist", "external"], LIST_TIMEOUT)
        if result is not None and result.returncode == 0:
            break
        logger.warning(
            "Listing external drives failed (attempt %d/%d)", attempt, LIST_RETRY_ATTEMPTS,
        )
        if attempt < LIST_RETRY_ATTEMPTS:
            time.sleep(1)

    if result is None or result.returncode != 0:
        logger.error("Giving up listing external drives after %d attempts", LIST_RETRY_ATTEMPTS)
        return

    boot_disk = _boot_disk_id()
    data = plistlib.loads(result.stdout)

    for disk_entry in data.get("AllDisksAndPartitions", []):
        disk_id = disk_entry.get("DeviceIdentifier")
        if not disk_id or disk_id == boot_disk:
            continue

        partitions = disk_entry.get("Partitions", [])
        if not partitions:
            continue

        # Prefer a mounted partition; fall back to the first partition
        # (unmounted) so the drive still shows up and can be mounted.
        chosen_info = None
        chosen_part_id = None

        for partition in partitions:
            part_id = partition.get("DeviceIdentifier")
            if not part_id:
                continue

            r = _diskutil(["info", "-plist", part_id], INFO_TIMEOUT)
            if r is None or r.returncode != 0:
                continue

            info = plistlib.loads(r.stdout)

            if info.get("MountPoint"):
                chosen_info = info
                chosen_part_id = part_id
                break
            elif chosen_info is None:
                chosen_info = info
                chosen_part_id = part_id

        if chosen_info is not None:
            yield DriveInfo(
                disk_id=disk_id,
                partition_id=chosen_part_id,
                volume_name=chosen_info.get("VolumeName") or "Unnamed",
                mount_point=chosen_info.get("MountPoint", ""),
                size_bytes=chosen_info.get("TotalSize", 0),
                filesystem=chosen_info.get("FilesystemType", ""),
            )


def mount_drive(drive: DriveInfo) -> None:
    r = _diskutil(["mount", drive.partition_id], ACTION_TIMEOUT)
    _require(r, f"Mounting {drive.partition_id}")


def unmount_drive(drive: DriveInfo) -> None:
    r = _diskutil(["unmount", drive.partition_id], ACTION_TIMEOUT)
    _require(r, f"Unmounting {drive.partition_id}")


def rename_drive(drive: DriveInfo, new_name: str) -> None:
    r = _diskutil(["rename", drive.partition_id, new_name], ACTION_TIMEOUT)
    _require(r, f"Renaming {drive.partition_id}")


def wipe_drive(drive: DriveInfo, new_name: str) -> None:
    # Last line of defense: never erase the disk the OS is running from,
    # no matter how this DriveInfo was constructed.
    if drive.disk_id == _boot_disk_id():
        raise RuntimeError(f"Refusing to wipe {drive.disk_id} — it's the startup disk.")
    r = _diskutil(
        ["eraseDisk", "FAT32", new_name, "MBRFormat", drive.disk_id],
        ERASE_TIMEOUT,
    )
    _require(r, f"Wiping {drive.disk_id}")


def refresh_drive_info(drive: DriveInfo) -> DriveInfo:
    # After wipe, the partition ID may have changed; re-discover from disk_id
    r = _diskutil(["list", "-plist", drive.disk_id], INFO_TIMEOUT)
    if r is None or r.returncode != 0:
        return drive

    data = plistlib.loads(r.stdout)
    for disk_entry in data.get("AllDisksAndPartitions", []):
        if disk_entry.get("DeviceIdentifier") != drive.disk_id:
            continue
        for partition in disk_entry.get("Partitions", []):
            part_id = partition.get("DeviceIdentifier")
            if not part_id:
                continue
            r2 = _diskutil(["info", "-plist", part_id], INFO_TIMEOUT)
            if r2 is None or r2.returncode != 0:
                continue
            info = plistlib.loads(r2.stdout)
            if info.get("MountPoint"):
                return DriveInfo(
                    disk_id=drive.disk_id,
                    partition_id=part_id,
                    volume_name=info.get("VolumeName", "Unnamed"),
                    mount_point=info.get("MountPoint", ""),
                    size_bytes=info.get("TotalSize", 0),
                    filesystem=info.get("FilesystemType", ""),
                )

    return drive
