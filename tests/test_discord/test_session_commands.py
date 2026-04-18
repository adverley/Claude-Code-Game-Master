import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from discord_bot.commands.session import handle_session_start, handle_session_end


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
