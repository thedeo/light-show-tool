import shutil
from pathlib import Path

CHUNK_SIZE = 1024 * 1024  # 1 MB


def copy_groups_to_drive(groups, drive, erase_first, progress_callback, cancel_check):
    mount = Path(drive.mount_point)

    if erase_first:
        for item in mount.iterdir():
            if cancel_check():
                raise InterruptedError("Cancelled")
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

    # Build flat list of (src, dest, size) from ShowFilePair items
    total_bytes = 0
    file_list = []
    for group in groups:
        dest_dir = mount / group.name
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
