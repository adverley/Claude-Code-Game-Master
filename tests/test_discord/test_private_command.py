import pytest
import discord
from unittest.mock import AsyncMock, MagicMock
from discord_bot.commands.private import handle_private


class FakeMessage:
    def __init__(self, user_id="111", display_name="Erik"):
        self.author = MagicMock()
        self.author.id = user_id
        self.author.display_name = display_name
        self.channel = MagicMock()
        self.channel.send = AsyncMock()


class FakeCtx:
    def __init__(self, character="thorin", discord_name="Erik"):
        self.player_map = MagicMock()
        self.player_map.get_character.return_value = character
        self.player_map.get_discord_name.return_value = discord_name
        self.message_buffer = MagicMock()
        self.message_buffer.format_for_claude.return_value = "[Discord context]\nActive player: Erik (thorin)\nQuestion: secret"
        self.config = {}
        self.claude_bridge = AsyncMock()
        self.claude_bridge.is_active = True
        self.claude_bridge.send = AsyncMock(return_value="Only you know the truth about the amulet.")
        mock_user = AsyncMock()
        mock_user.send = AsyncMock()
        self.client = AsyncMock()
        self.client.fetch_user = AsyncMock(return_value=mock_user)


@pytest.mark.asyncio
class TestPrivateCommand:
    async def test_dms_response_to_player(self):
        msg = FakeMessage()
        ctx = FakeCtx()

        await handle_private(msg, "what do I know about the amulet?", ctx)

        ctx.client.fetch_user.assert_called_once_with(int("111"))
        dm_user = ctx.client.fetch_user.return_value
        dm_user.send.assert_called_once()
        dm_text = dm_user.send.call_args[0][0]
        assert "amulet" in dm_text

    async def test_posts_whisper_ack_to_channel(self):
        msg = FakeMessage()
        ctx = FakeCtx()

        await handle_private(msg, "my secret question", ctx)

        channel_calls = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("whispers" in c.lower() or "🤫" in c for c in channel_calls)

    async def test_rejects_unregistered_player(self):
        msg = FakeMessage()
        ctx = FakeCtx(character=None)

        await handle_private(msg, "secret", ctx)

        ctx.claude_bridge.send.assert_not_called()
        sent_text = msg.channel.send.call_args[0][0]
        assert "!join" in sent_text

    async def test_rejects_when_no_session(self):
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.claude_bridge.is_active = False

        await handle_private(msg, "secret", ctx)

        ctx.claude_bridge.send.assert_not_called()
        sent_text = msg.channel.send.call_args[0][0]
        assert "session-start" in sent_text

    async def test_handles_dms_disabled(self):
        msg = FakeMessage()
        ctx = FakeCtx()
        forbidden_response = MagicMock()
        forbidden_response.status = 403
        forbidden_response.reason = "Forbidden"
        dm_user = AsyncMock()
        dm_user.send.side_effect = discord.Forbidden(forbidden_response, "Cannot send messages to this user")
        ctx.client.fetch_user = AsyncMock(return_value=dm_user)

        await handle_private(msg, "secret", ctx)

        channel_calls = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("DMs are closed" in c or "enable" in c.lower() for c in channel_calls)
