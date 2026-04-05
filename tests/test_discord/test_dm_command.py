import pytest
from unittest.mock import AsyncMock, MagicMock
from discord_bot.commands.dm import handle_dm


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
        self.message_buffer.get_delta.return_value = [
            {"timestamp": "14:32", "discord_name": "Erik", "character_name": "thorin", "content": "let's go", "is_command": False}
        ]
        self.message_buffer.format_for_claude.return_value = "[Discord context]\nActive player: Erik (thorin)\nCommand: I search"
        self.claude_bridge = AsyncMock()
        self.claude_bridge.is_active = True
        self.claude_bridge.send = AsyncMock(return_value="You find a hidden door behind the bookshelf.")


@pytest.mark.asyncio
class TestDmCommand:
    async def test_sends_to_claude_and_replies(self):
        msg = FakeMessage()
        ctx = FakeCtx()

        await handle_dm(msg, "I search the room", ctx)

        ctx.claude_bridge.send.assert_called_once()
        # Response should contain Claude's reply (thinking msg deleted + response sent)
        calls = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("hidden door" in c for c in calls)

    async def test_rejects_unregistered_player(self):
        msg = FakeMessage()
        ctx = FakeCtx(character=None)

        await handle_dm(msg, "I search", ctx)

        ctx.claude_bridge.send.assert_not_called()
        sent_text = msg.channel.send.call_args[0][0]
        assert "!join" in sent_text

    async def test_rejects_when_no_session(self):
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.claude_bridge.is_active = False

        await handle_dm(msg, "I search", ctx)

        ctx.claude_bridge.send.assert_not_called()
        sent_text = msg.channel.send.call_args[0][0]
        assert "session-start" in sent_text
