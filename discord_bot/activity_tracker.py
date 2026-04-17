from datetime import datetime, timezone
from enum import Enum


class ActivityTracker:
    def __init__(self):
        self._last_seen: dict[str, datetime] = {}

    def record(self, user_id: str) -> None:
        self._last_seen[user_id] = datetime.now(timezone.utc)

    def active_since(self, cutoff: datetime) -> set[str]:
        return {uid for uid, ts in self._last_seen.items() if ts >= cutoff}


class Pace(Enum):
    ACTIVE = 120
    ASYNC = 3600
