import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from discord_bot.commands.session import handle_session_start, handle_session_end


def _make_reaction(emoji: str, msg_id: int, user_id: str):
    reaction = MagicMock()
    reaction.emoji = emoji
    reaction.message = MagicMock()
    reaction.message.id = msg_id
    user = MagicMock()
    user.id = user_id
    return reaction, user


class FakeMessage:
    def __init__(self, user_id="111"):
        self.author = MagicMock()
        self.author.id = user_id
        self.author.display_name = "Erik"
        self.channel = MagicMock()
        self.channel.send = AsyncMock()


class FakeCtx:
    def __init__(self, active=False):
        from discord_bot.activity_tracker import ActivityTracker, Pace
        self.claude_bridge = MagicMock()
        self.claude_bridge.is_active = active
        self.claude_bridge.start_session = MagicMock(return_value="discord-test-123")
        self.claude_bridge.send_init = AsyncMock(return_value="Welcome adventurers! You stand at the entrance of a dark cave.")
        self.claude_bridge.send = AsyncMock(return_value="Session ended. The party rests for the night.")
        self.claude_bridge.end_session = MagicMock()
        self.claude_bridge._project_dir = "/fake/path"
        self.player_map = MagicMock()
        self.player_map.get_all.return_value = {
            "111": {"discord_name": "Erik", "character": "thorin"}
        }
        self.config = {}
        self.campaign_dir = Path("world-state/campaigns/test-campaign")
        mock_dm_user = AsyncMock()
        mock_dm_user.send = AsyncMock()
        self.client = AsyncMock()
        self.client.fetch_user = AsyncMock(return_value=mock_dm_user)
        self.activity_tracker = ActivityTracker()
        self.session_end_pending = False


@pytest.mark.asyncio
class TestSessionStart:
    async def test_starts_session_and_posts_narration(self):
        msg = FakeMessage()
        ctx = FakeCtx(active=False)

        await handle_session_start(msg, "", ctx)

        ctx.claude_bridge.start_session.assert_called_once_with("test-campaign")
        ctx.claude_bridge.send_init.assert_called_once()
        # Should post the opening narration
        calls = [str(c) for c in msg.channel.send.call_args_list]
        assert any("Welcome" in c or "adventurers" in c for c in calls)

    async def test_rejects_if_session_already_active(self):
        msg = FakeMessage()
        ctx = FakeCtx(active=True)

        await handle_session_start(msg, "", ctx)

        ctx.claude_bridge.start_session.assert_not_called()
        sent = msg.channel.send.call_args[0][0]
        assert "already" in sent.lower()


@pytest.mark.asyncio
class TestSessionEnd:
    async def test_ends_session_and_posts_summary(self):
        msg = FakeMessage()
        ctx = FakeCtx(active=True)

        await handle_session_end(msg, "We defeated the goblins", ctx)

        ctx.claude_bridge.send.assert_called_once()
        ctx.claude_bridge.end_session.assert_called_once()

    async def test_rejects_if_no_active_session(self):
        msg = FakeMessage()
        ctx = FakeCtx(active=False)

        await handle_session_end(msg, "", ctx)

        ctx.claude_bridge.send.assert_not_called()
        sent = msg.channel.send.call_args[0][0]
        assert "no active session" in sent.lower() or "session-start" in sent.lower()

    async def test_session_end_pending_flag_exists_on_ctx(self):
        from discord_bot.bot import BotContext
        from discord_bot.activity_tracker import ActivityTracker, Pace
        from dataclasses import fields
        field_names = {f.name for f in fields(BotContext)}
        assert "session_end_pending" in field_names


@pytest.mark.asyncio
class TestSessionEndGate:
    async def test_no_other_active_players_ends_immediately(self):
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx(active=True)
        # No other players recorded in activity tracker

        await handle_session_end(msg, "we won", ctx)

        ctx.claude_bridge.send.assert_called_once()
        ctx.claude_bridge.end_session.assert_called_once()
        # Gate was skipped — no confirmation message posted
        texts = [c[0][0] for c in msg.channel.send.call_args_list]
        assert not any("react" in t.lower() or "confirm" in t.lower() for t in texts)

    async def test_rejects_when_already_pending(self):
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx(active=True)
        ctx.session_end_pending = True

        await handle_session_end(msg, "we won", ctx)

        ctx.claude_bridge.send.assert_not_called()
        text = msg.channel.send.call_args[0][0]
        assert "pending" in text.lower()

    async def test_majority_confirm_ends_session(self):
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx(active=True)
        ctx.player_map.get_all.return_value = {
            "111": {"discord_name": "Erik", "character": "thorin"},
            "222": {"discord_name": "Kira", "character": "elara"},
            "333": {"discord_name": "Brom", "character": "brom"},
        }
        ctx.activity_tracker.record("222")
        ctx.activity_tracker.record("333")

        confirm_msg = AsyncMock()
        confirm_msg.id = 999
        msg.channel.send = AsyncMock(return_value=confirm_msg)

        # "222" confirms — that's 1 out of 2 candidates = exactly 50%, not majority
        # "333" also confirms — that's 2 out of 2 = majority
        reactions = [
            _make_reaction("✅", 999, "222"),
            _make_reaction("✅", 999, "333"),
        ]
        ctx.client.wait_for = AsyncMock(side_effect=reactions)

        await handle_session_end(msg, "we won", ctx)

        ctx.claude_bridge.send.assert_called_once()
        ctx.claude_bridge.end_session.assert_called_once()
        assert ctx.session_end_pending is False

    async def test_single_deny_aborts(self):
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx(active=True)
        ctx.player_map.get_all.return_value = {
            "111": {"discord_name": "Erik", "character": "thorin"},
            "222": {"discord_name": "Kira", "character": "elara"},
        }
        ctx.player_map.get_discord_name.return_value = "Kira"
        ctx.activity_tracker.record("222")

        confirm_msg = AsyncMock()
        confirm_msg.id = 999
        msg.channel.send = AsyncMock(return_value=confirm_msg)

        reaction, user = _make_reaction("❌", 999, "222")
        ctx.client.wait_for = AsyncMock(return_value=(reaction, user))

        await handle_session_end(msg, "we won", ctx)

        ctx.claude_bridge.send.assert_not_called()
        ctx.claude_bridge.end_session.assert_not_called()
        assert ctx.session_end_pending is False
        texts = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("denied" in t.lower() or "aborted" in t.lower() for t in texts)

    async def test_timeout_without_majority_aborts(self):
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx(active=True)
        ctx.player_map.get_all.return_value = {
            "111": {"discord_name": "Erik", "character": "thorin"},
            "222": {"discord_name": "Kira", "character": "elara"},
            "333": {"discord_name": "Brom", "character": "brom"},
        }
        ctx.activity_tracker.record("222")
        ctx.activity_tracker.record("333")

        confirm_msg = AsyncMock()
        confirm_msg.id = 999
        msg.channel.send = AsyncMock(return_value=confirm_msg)

        # Only 1 of 2 confirms, then timeout — not a majority
        reactions = [
            _make_reaction("✅", 999, "222"),
            asyncio.TimeoutError,
        ]

        call_count = 0
        async def side_effect(*a, **kw):
            nonlocal call_count
            val = reactions[min(call_count, len(reactions) - 1)]
            call_count += 1
            if val is asyncio.TimeoutError:
                raise asyncio.TimeoutError
            return val

        ctx.client.wait_for = side_effect

        await handle_session_end(msg, "we won", ctx)

        ctx.claude_bridge.send.assert_not_called()
        assert ctx.session_end_pending is False
        texts = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("timed out" in t.lower() or "aborted" in t.lower() for t in texts)

    async def test_pending_flag_cleared_after_deny(self):
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx(active=True)
        ctx.player_map.get_all.return_value = {
            "111": {"discord_name": "Erik", "character": "thorin"},
            "222": {"discord_name": "Kira", "character": "elara"},
        }
        ctx.player_map.get_discord_name.return_value = "Kira"
        ctx.activity_tracker.record("222")

        confirm_msg = AsyncMock()
        confirm_msg.id = 999
        msg.channel.send = AsyncMock(return_value=confirm_msg)

        reaction, user = _make_reaction("❌", 999, "222")
        ctx.client.wait_for = AsyncMock(return_value=(reaction, user))

        await handle_session_end(msg, "we won", ctx)

        assert ctx.session_end_pending is False

    async def test_check_closure_filters_correctly(self):
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx(active=True)
        ctx.player_map.get_all.return_value = {
            "111": {"discord_name": "Erik", "character": "thorin"},
            "222": {"discord_name": "Kira", "character": "elara"},
        }
        ctx.activity_tracker.record("222")

        confirm_msg = AsyncMock()
        confirm_msg.id = 999
        msg.channel.send = AsyncMock(return_value=confirm_msg)

        captured_check = None

        async def capture_wait_for(event, *, check, timeout=None):
            nonlocal captured_check
            captured_check = check
            raise asyncio.TimeoutError  # bail out immediately

        ctx.client.wait_for = capture_wait_for

        await handle_session_end(msg, "we won", ctx)

        assert captured_check is not None

        # Valid: correct message, candidate user, confirm emoji
        valid_reaction, valid_user = _make_reaction("✅", 999, "222")
        assert captured_check(valid_reaction, valid_user) is True

        # Wrong message ID
        wrong_msg_reaction, _ = _make_reaction("✅", 888, "222")
        assert captured_check(wrong_msg_reaction, valid_user) is False

        # Non-candidate user
        non_candidate_reaction, non_candidate_user = _make_reaction("✅", 999, "999")
        assert captured_check(non_candidate_reaction, non_candidate_user) is False

        # Wrong emoji
        wrong_emoji_reaction, _ = _make_reaction("🎲", 999, "222")
        assert captured_check(wrong_emoji_reaction, valid_user) is False
