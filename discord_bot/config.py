"""Load and validate bot configuration."""

import json
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = ["bot_token", "channel_id", "campaign"]
DEFAULTS = {
    "message_buffer_size": 50,
    "dm_player": "",   # Discord display name allowed to use !dm. Empty = anyone.
    "model": "",       # Claude model to use. Empty = Claude Code default. E.g. "sonnet", "opus", "haiku"
}


def load_config(path: Path) -> dict[str, Any]:
    """Load config from JSON file, validate required fields, apply defaults."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for field in REQUIRED_FIELDS:
        if field not in data:
            raise ValueError(f"Missing required config field: {field}")

    for key, default in DEFAULTS.items():
        data.setdefault(key, default)

    return data
