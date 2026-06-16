import subprocess
import plistlib
from .models import DriveInfo


def list_external_drives() -> list:
    try:
        result = subprocess.run(
            ["diskutil", "list", "-plist", "external"],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return []

    data = plistlib.loads(result.stdout)
    drives = []

    for disk_entry in data.get("AllDisksAndPartitions", []):
        disk_id = disk_entry.get("DeviceIdentifier")
        if not disk_id:
            continue

        for partition in disk_entry.get("Partitions", []):
            part_id = partition.get("DeviceIdentifier")
            if not part_id:
                continue

            r = subprocess.run(
                ["diskutil", "info", "-plist", part_id],
                capture_output=True,
            )
            if r.returncode != 0:
                continue

            info = plistlib.loads(r.stdout)
            if info.get("MountPoint"):
                drives.append(DriveInfo(
                    disk_id=disk_id,
                    partition_id=part_id,
                    volume_name=info.get("VolumeName", "Unnamed"),
                    mount_point=info.get("MountPoint", ""),
                    size_bytes=info.get("TotalSize", 0),
                    filesystem=info.get("FilesystemType", ""),
                ))
                break  # use the first mountable partition

    return drives


def rename_drive(drive: DriveInfo, new_name: str) -> None:
    subprocess.run(
        ["diskutil", "rename", drive.partition_id, new_name],
        check=True,
        capture_output=True,
    )


def wipe_drive(drive: DriveInfo, new_name: str) -> None:
    subprocess.run(
        ["diskutil", "eraseDisk", "FAT32", new_name, "MBRFormat", drive.disk_id],
        check=True,
        capture_output=True,
    )


def refresh_drive_info(drive: DriveInfo) -> DriveInfo:
    # After wipe, the partition ID may have changed; re-discover from disk_id
    r = subprocess.run(
        ["diskutil", "list", "-plist", drive.disk_id],
        capture_output=True,
    )
    if r.returncode != 0:
        return drive

    data = plistlib.loads(r.stdout)
    for disk_entry in data.get("AllDisksAndPartitions", []):
        if disk_entry.get("DeviceIdentifier") != drive.disk_id:
            continue
        for partition in disk_entry.get("Partitions", []):
            part_id = partition.get("DeviceIdentifier")
            if not part_id:
                continue
            r2 = subprocess.run(
                ["diskutil", "info", "-plist", part_id],
                capture_output=True,
            )
            if r2.returncode != 0:
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
