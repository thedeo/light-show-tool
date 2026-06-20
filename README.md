# Light Show Tool

A macOS desktop app for managing light show files across multiple USB thumb drives simultaneously. Supports copying, renaming, and wiping drives in bulk.

![Copy Mode](screenshots/copy-mode.png)

## Requirements

- macOS (uses `diskutil` for drive management)
- Python 3.10+

## Install

```bash
git clone https://github.com/thedeo/light-show-tool.git
cd light-show-tool
make install
```

This creates a local virtual environment (`.venv`) and installs dependencies into it.

## Run

```bash
make run
```

## Drives

The drive list shows every connected external drive by its mount-point name, with a live count in the header (e.g. *Drives (3 of 16 selected)*). Any drive whose filesystem isn't Tesla-compatible (FAT32/exFAT) is flagged with a warning icon and tooltip. Unmounted drives can't be selected for an operation until they're mounted.

A colored status dot next to each drive shows its state at a glance:

- 🔵 **Blue** — mounted and loaded, not yet copied this session
- 🟢 **Green** — copied to successfully
- 🟠 **Orange** — last copy to this drive failed
- 🔴 **Red** — unmounted (must be mounted before it can be selected)

Buttons:

- **All / None** — select or deselect every mounted drive
- **Refresh** — force a full rescan of connected drives
- **Mount All / Unmount All** — bulk mount or unmount every drive in one action (unmounting asks for confirmation first)

Drive scanning runs in the background, so the app stays responsive even if `diskutil` is slow to respond. The list also **auto-updates as drives are plugged in or pulled** — newly attached drives are slotted into natural disk order (`disk4`, `disk5`, … `disk10`) without a full rescan, and your current selection is preserved across updates. Detection polls in the background and is suspended entirely while any operation is running, so it never disturbs an in-progress copy.

## Modes

### Copy
Drag `.fseq` or audio (`.mp3` / `.wav`) files into a group — the app automatically detects and pairs the matching file by name. Each pair is one *show*. Multiple groups can be created and selectively included or excluded per copy operation, and the confirmation dialog summarizes how many shows each group contains.

Before copying, choose how to handle each drive's existing contents:
- **Don't erase** — copy on top of whatever's already there
- **Delete existing files (fast)** — clear the drive's contents (keeping its current format) before copying; much faster than a full reformat
- **Format drive (slow, full reformat)** — erase and reformat as FAT32 before copying; required for drives flagged as not Tesla-compatible

The optional **Eject when done** checkbox unmounts each drive the moment its copy finishes (which also forces a final flush), so it's safe to pull without a separate unmount step.

Progress is shown both per-drive — naming the drive currently copying and its position (*Copying drive 4 of 16*) — and as an overall completion count across all selected drives. While a copy is running you can:

- **Skip Drive** — abort the current drive (after a confirmation) and move on to the next; the skipped drive isn't retried
- **Cancel** — stop the whole run

Reliability features during a copy:

- **Stalled-drive detection** — if a drive stops accepting writes for 15 seconds (a sign it's faulty or was unplugged), the copy to it is aborted immediately instead of hanging
- **Automatic retry** — drives that fail are retried once at the end of the run, after every other drive has finished
- Each drive's mount point is re-resolved right before copying, so a drive that remounted under a different path is still written correctly

### Rename
Rename all selected drives to the same FAT32 label (max 11 characters).

### Wipe
Erase and reformat selected drives as FAT32. Requires an explicit confirmation checkbox before proceeding.

## Safety

Wipe and "delete existing files" are destructive, so the app guards against ever touching the wrong disk:

- The drive list only ever includes external, non-boot disks — even if your Mac boots from an external drive, that disk is detected and excluded automatically
- `wipe_drive` and the file-delete path both independently refuse to run against the startup disk or an empty/root mount path, regardless of how a drive entry was produced
- Every destructive action (Wipe, erase-before-copy, Unmount All) shows a confirmation dialog listing every targeted drive by name before proceeding; Wipe additionally requires checking "I understand this is permanent"

## Troubleshooting

Every run writes a fresh `light_show_tool.log` in the project folder (overwritten each launch, so it only ever holds the latest run). It records every `diskutil` call, drive scan, and copy/erase operation, including full error details when something fails — check it first if a drive errors out.

## File Pairing

Light show sequences consist of a `.fseq` file and an audio file with the same base name:

```
01-Seven-Nation-Army.fseq
01-Seven-Nation-Army.mp3
```

Drop either file and the app will locate the other automatically. If the paired file is missing or misnamed, you'll see an error with details.

## Saved State

The app remembers your setup between launches in `state.json` (in the project folder):

- Your groups and their file pairs, plus which groups are checked
- Copy mode: the chosen erase mode and the **Eject when done** setting
- Rename mode: the last label entered
- Wipe mode: the last volume label
- The last-used mode (Copy / Rename / Wipe) and the window size and position

This file is written automatically; deleting it simply resets the app to defaults.

## Notes

- Drive detection is fully dynamic — no disk identifiers are hardcoded
- FAT32 labels are uppercased automatically by `diskutil`
- The app requires permission to run `diskutil` commands (standard on macOS for the logged-in user)
- All `diskutil` calls are timeout-bounded and run off the main thread, so a slow or unresponsive drive can't freeze the app
- macOS-managed metadata folders (`.Spotlight-V100`, `.fseventsd`, `.Trashes`, etc.) are left alone when clearing a drive's contents, since they're permission-protected and recreated automatically
