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
        self.progress_pending = False
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


def _make_reaction(emoji: str, msg_id: int, user_id: str):
    reaction = MagicMock()
    reaction.emoji = emoji
    reaction.message = MagicMock()
    reaction.message.id = msg_id
    user = MagicMock()
    user.id = user_id
    return reaction, user


@pytest.mark.asyncio
class TestProgressCommand:
    async def test_no_active_players_proceeds_without_confirmation(self):
        from discord_bot.commands.progress import handle_progress
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx()
        # Empty tracker — no other active players

        await handle_progress(msg, "we enter the cave", ctx)

        ctx.claude_bridge.send.assert_called_once()
        ctx.client.wait_for.assert_not_called()

    async def test_rejects_when_already_pending(self):
        from discord_bot.commands.progress import handle_progress
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.progress_pending = True

        await handle_progress(msg, "anything", ctx)

        ctx.claude_bridge.send.assert_not_called()
        text = msg.channel.send.call_args[0][0]
        assert "pending" in text.lower()

    async def test_rejects_unregistered_player(self):
        from discord_bot.commands.progress import handle_progress
        msg = FakeMessage()
        ctx = FakeCtx(character=None)

        await handle_progress(msg, "we attack", ctx)

        ctx.claude_bridge.send.assert_not_called()
        text = msg.channel.send.call_args[0][0]
        assert "!join" in text

    async def test_rejects_when_no_active_session(self):
        from discord_bot.commands.progress import handle_progress
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.claude_bridge.is_active = False

        await handle_progress(msg, "we attack", ctx)

        ctx.claude_bridge.send.assert_not_called()
        text = msg.channel.send.call_args[0][0]
        assert "session-start" in text

    async def test_dm_player_guard_blocks_non_dm(self):
        from discord_bot.commands.progress import handle_progress
        msg = FakeMessage(display_name="RandomPlayer")
        ctx = FakeCtx()
        ctx.config = {"dm_player": "GameMaster"}

        await handle_progress(msg, "advance", ctx)

        ctx.claude_bridge.send.assert_not_called()
        text = msg.channel.send.call_args[0][0]
        assert "GameMaster" in text

    async def test_all_active_players_confirm_advances_plot(self):
        from discord_bot.commands.progress import handle_progress
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx()
        ctx.player_map.get_all.return_value = {
            "111": {"discord_name": "DM", "character": "Thorin"},
            "222": {"discord_name": "Player2", "character": "Elara"},
        }
        ctx.activity_tracker.record("222")

        confirm_msg = AsyncMock()
        confirm_msg.id = 999
        msg.channel.send = AsyncMock(return_value=confirm_msg)

        reaction, user = _make_reaction("✅", 999, "222")
        ctx.client.wait_for = AsyncMock(return_value=(reaction, user))

        await handle_progress(msg, "we move north", ctx)

        ctx.claude_bridge.send.assert_called_once()
        assert ctx.progress_pending is False

    async def test_deny_aborts_and_posts_message(self):
        from discord_bot.commands.progress import handle_progress
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx()
        ctx.player_map.get_all.return_value = {
            "111": {"discord_name": "DM", "character": "Thorin"},
            "222": {"discord_name": "Player2", "character": "Elara"},
        }
        ctx.activity_tracker.record("222")

        confirm_msg = AsyncMock()
        confirm_msg.id = 999
        msg.channel.send = AsyncMock(return_value=confirm_msg)

        reaction, user = _make_reaction("❌", 999, "222")
        ctx.client.wait_for = AsyncMock(return_value=(reaction, user))

        await handle_progress(msg, "we move north", ctx)

        ctx.claude_bridge.send.assert_not_called()
        assert ctx.progress_pending is False
        texts = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("denied" in t.lower() or "aborted" in t.lower() for t in texts)

    async def test_timeout_proceeds_without_full_confirmation(self):
        from discord_bot.commands.progress import handle_progress
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx()
        ctx.player_map.get_all.return_value = {
            "111": {"discord_name": "DM", "character": "Thorin"},
            "222": {"discord_name": "Player2", "character": "Elara"},
        }
        ctx.activity_tracker.record("222")
        ctx.pace = Pace.ACTIVE

        confirm_msg = AsyncMock()
        confirm_msg.id = 999
        msg.channel.send = AsyncMock(return_value=confirm_msg)

        ctx.client.wait_for = AsyncMock(side_effect=asyncio.TimeoutError)

        await handle_progress(msg, "we move north", ctx)

        ctx.claude_bridge.send.assert_called_once()
        assert ctx.progress_pending is False

    async def test_pending_flag_cleared_after_deny(self):
        from discord_bot.commands.progress import handle_progress
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx()
        ctx.player_map.get_all.return_value = {
            "111": {"discord_name": "DM", "character": "Thorin"},
            "222": {"discord_name": "Player2", "character": "Elara"},
        }
        ctx.activity_tracker.record("222")

        confirm_msg = AsyncMock()
        confirm_msg.id = 999
        msg.channel.send = AsyncMock(return_value=confirm_msg)

        reaction, user = _make_reaction("❌", 999, "222")
        ctx.client.wait_for = AsyncMock(return_value=(reaction, user))

        await handle_progress(msg, "we move", ctx)

        assert ctx.progress_pending is False

    async def test_check_closure_filters_correctly(self):
        from discord_bot.commands.progress import handle_progress
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx()
        ctx.player_map.get_all.return_value = {
            "111": {"discord_name": "DM", "character": "Thorin"},
            "222": {"discord_name": "Player2", "character": "Elara"},
        }
        ctx.activity_tracker.record("222")

        confirm_msg = AsyncMock()
        confirm_msg.id = 999
        msg.channel.send = AsyncMock(return_value=confirm_msg)

        captured_check = None

        async def capture_wait_for(event, *, check, timeout=None):
            nonlocal captured_check
            captured_check = check
            raise asyncio.TimeoutError  # proceed immediately

        ctx.client.wait_for = capture_wait_for

        await handle_progress(msg, "we move", ctx)

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
