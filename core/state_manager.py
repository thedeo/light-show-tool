import json
from pathlib import Path

STATE_FILE = Path(__file__).parent.parent / "state.json"


def _read_all() -> dict:
    """Return the whole state document, or {} if missing/corrupt."""
    if not STATE_FILE.exists():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_all(data: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(data, indent=2))
    except OSError:
        pass


def save_state(state_data: list) -> None:
    """Persist group state. Preserves any saved settings already on disk."""
    data = _read_all()
    data["groups"] = state_data
    _write_all(data)


def load_state() -> list:
    """Return list of group dicts from the state file, or [] if missing/corrupt."""
    return _read_all().get("groups", [])


def save_settings(settings: dict) -> None:
    """Merge the given UI settings into the state file. Preserves groups and
    any settings keys not present in `settings`."""
    data = _read_all()
    merged = data.get("settings", {})
    if not isinstance(merged, dict):
        merged = {}
    merged.update(settings)
    data["settings"] = merged
    _write_all(data)


def load_settings() -> dict:
    """Return the saved UI settings dict, or {} if none."""
    settings = _read_all().get("settings", {})
    return settings if isinstance(settings, dict) else {}
