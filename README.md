# Light Show Tool

A macOS desktop app for managing light show files across multiple USB thumb drives simultaneously. Supports copying, renaming, and wiping drives in bulk.

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

## Modes

### Copy
Drag `.fseq` or audio (`.mp3` / `.wav`) files into a group — the app automatically detects and pairs the matching file by name. Multiple groups can be created and selectively included or excluded per copy operation.

### Rename
Rename all selected drives to the same FAT32 label (max 11 characters).

### Wipe
Erase and reformat selected drives as FAT32. Requires an explicit confirmation checkbox before proceeding.

## File Pairing

Light show sequences consist of a `.fseq` file and an audio file with the same base name:

```
01-Seven-Nation-Army.fseq
01-Seven-Nation-Army.mp3
```

Drop either file and the app will locate the other automatically. If the paired file is missing or misnamed, you'll see an error with details.

## Notes

- Drive detection is fully dynamic — no disk identifiers are hardcoded
- FAT32 labels are uppercased automatically by `diskutil`
- The app requires permission to run `diskutil` commands (standard on macOS for the logged-in user)
