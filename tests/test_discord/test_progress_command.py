import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from discord_bot.activity_tracker import ActivityTracker, Pace


class FakeMessage:
    def __init__(self, user_id="111", display_name="DM"):
        self.author = MagicMock()
        self.author.id = user_id
        self.author.display_name = display_name
        self.channel = MagicMock()
        self.channel.send = AsyncMock()


class FakeCtx:
    def __init__(self, character="Thorin", discord_name="DM"):
        self.player_map = MagicMock()
        self.player_map.get_character.return_value = character
        self.player_map.get_discord_name.return_value = discord_name
        self.player_map.get_all.return_value = {
            "111": {"discord_name": discord_name, "character": character}
        }
        self.config = {}
        self.claude_bridge = AsyncMock()
        self.claude_bridge.is_active = True
        self.claude_bridge.send = AsyncMock(return_value="The plot thickens.")
        self.message_buffer = MagicMock()
        self.message_buffer.get_delta.return_value = []
        self.message_buffer.format_for_claude.return_value = "payload"
        self.activity_tracker = ActivityTracker()
        self.pace = Pace.ACTIVE
        self.pending_gates = set()
        self.client = AsyncMock()
        self.private_chat_manager = MagicMock()
        self.private_chat_manager.build_process_notes.return_value = ""


@pytest.mark.asyncio
class TestPaceCommand:
    async def test_set_active(self):
        from discord_bot.commands.progress import handle_pace
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.pace = Pace.ASYNC

        await handle_pace(msg, "active", ctx)

        assert ctx.pace == Pace.ACTIVE
        text = msg.channel.send.call_args[0][0]
        assert "active" in text.lower()

    async def test_set_async(self):
        from discord_bot.commands.progress import handle_pace
        msg = FakeMessage()
        ctx = FakeCtx()

        await handle_pace(msg, "async", ctx)

        assert ctx.pace == Pace.ASYNC
        text = msg.channel.send.call_args[0][0]
        assert "async" in text.lower()

    async def test_no_args_shows_current_mode_and_timeout(self):
        from discord_bot.commands.progress import handle_pace
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.pace = Pace.ACTIVE

        await handle_pace(msg, "", ctx)

        text = msg.channel.send.call_args[0][0]
        assert "active" in text.lower()
        assert "2" in text

    async def test_unknown_arg_shows_current_mode(self):
        from discord_bot.commands.progress import handle_pace
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.pace = Pace.ASYNC

        await handle_pace(msg, "turbo", ctx)

        text = msg.channel.send.call_args[0][0]
        assert "async" in text.lower()


