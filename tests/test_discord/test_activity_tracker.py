import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from datetime import datetime, timedelta, timezone
from discord_bot.activity_tracker import ActivityTracker, Pace


class TestActivityTracker:
    def test_record_marks_user_active(self):
        tracker = ActivityTracker()
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=1)
        tracker.record("user1")
        assert "user1" in tracker.active_since(cutoff)

    def test_old_activity_not_returned(self):
        tracker = ActivityTracker()
        tracker._last_seen["user1"] = datetime.now(timezone.utc) - timedelta(minutes=20)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
        assert "user1" not in tracker.active_since(cutoff)

    def test_multiple_users_tracked_independently(self):
        tracker = ActivityTracker()
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=1)
        tracker.record("user1")
        tracker.record("user2")
        active = tracker.active_since(cutoff)
        assert "user1" in active
        assert "user2" in active

    def test_record_updates_stale_user(self):
        tracker = ActivityTracker()
        tracker._last_seen["user1"] = datetime.now(timezone.utc) - timedelta(minutes=20)
        tracker.record("user1")
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
        assert "user1" in tracker.active_since(cutoff)

    def test_empty_tracker_returns_empty_set(self):
        tracker = ActivityTracker()
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
        assert tracker.active_since(cutoff) == set()


class TestPace:
    def test_active_timeout_is_two_minutes(self):
        assert Pace.ACTIVE.value == 120

    def test_async_timeout_is_one_hour(self):
        assert Pace.ASYNC.value == 3600
