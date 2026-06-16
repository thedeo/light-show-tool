import json
from pathlib import Path

STATE_FILE = Path(__file__).parent.parent / "state.json"


def save_state(state_data: list) -> None:
    """Persist group state to disk. state_data is a list of dicts."""
    try:
        STATE_FILE.write_text(json.dumps({"groups": state_data}, indent=2))
    except OSError:
        pass


def load_state() -> list:
    """Return list of group dicts from the state file, or [] if missing/corrupt."""
    if not STATE_FILE.exists():
        return []
    try:
        data = json.loads(STATE_FILE.read_text())
        return data.get("groups", [])
    except Exception:
        return []
