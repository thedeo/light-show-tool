import subprocess
import plistlib
from .models import DriveInfo

# diskutil calls are normally near-instant, but can wedge under heavy
# Finder/diskarbitrationd lock contention (seen with 16+ simultaneously
# mounted drives). Every call is timeout-bounded so a stuck diskutil can
# never hang the app indefinitely.
INFO_TIMEOUT = 5
ACTION_TIMEOUT = 20
ERASE_TIMEOUT = 180


def _diskutil(args: list, timeout: float):
    """Run diskutil, returning CompletedProcess or None on timeout."""
    try:
        return subprocess.run(
            ["diskutil", *args],
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None


def _require(r, action: str) -> None:
    if r is None:
        raise TimeoutError(f"{action} timed out — diskutil did not respond.")
    if r.returncode != 0:
        msg = r.stderr.decode(errors="replace").strip()
        raise RuntimeError(msg or f"{action} failed.")


def list_external_drives() -> list:
    result = _diskutil(["list", "-plist", "external"], INFO_TIMEOUT)
    if result is None or result.returncode != 0:
        return []

    data = plistlib.loads(result.stdout)
    drives = []

    for disk_entry in data.get("AllDisksAndPartitions", []):
        disk_id = disk_entry.get("DeviceIdentifier")
        if not disk_id:
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
            drives.append(DriveInfo(
                disk_id=disk_id,
                partition_id=chosen_part_id,
                volume_name=chosen_info.get("VolumeName") or "Unnamed",
                mount_point=chosen_info.get("MountPoint", ""),
                size_bytes=chosen_info.get("TotalSize", 0),
                filesystem=chosen_info.get("FilesystemType", ""),
            ))

    return drives


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
