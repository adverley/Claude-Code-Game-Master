import pytest
import discord
from unittest.mock import AsyncMock, MagicMock
from discord_bot.commands.dm import handle_dm, handle_process


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
        self.player_map.get_user_id_by_character = MagicMock(return_value=None)
        self.message_buffer = MagicMock()
        self.message_buffer.get_delta.return_value = [
            {"timestamp": "14:32", "discord_name": "Erik", "character_name": "thorin", "content": "let's go"}
        ]
        self.message_buffer.format_for_claude.return_value = "[Discord context]\nActive player: Erik (thorin)\nQuestion: I search"
        self.config = {}
        self.claude_bridge = AsyncMock()
        self.claude_bridge.is_active = True
        self.claude_bridge.send = AsyncMock(return_value="You find a hidden door behind the bookshelf.")
        mock_dm_user = AsyncMock()
        mock_dm_user.send = AsyncMock()
        self.client = AsyncMock()
        self.client.fetch_user = AsyncMock(return_value=mock_dm_user)


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


@pytest.mark.asyncio
class TestDmCommandRouting:
    async def test_public_text_posted_to_channel(self):
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.claude_bridge.send = AsyncMock(return_value="The door creaks open.")

        await handle_dm(msg, "I open the door", ctx)

        # thinking_msg is the first channel.send call (the "thinking" indicator)
        thinking_msg = msg.channel.send.return_value
        thinking_msg.delete.assert_called_once()

        calls = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("door" in c for c in calls)

    async def test_private_marker_sends_dm_not_channel(self):
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.player_map.get_user_id_by_character = MagicMock(return_value="111")
        ctx.claude_bridge.send = AsyncMock(
            return_value="The party moves on.[PRIVATE:thorin]You notice a trapdoor.[/PRIVATE]"
        )

        await handle_dm(msg, "we enter the room", ctx)

        # Channel should NOT contain the private text
        channel_calls = [c[0][0] for c in msg.channel.send.call_args_list]
        assert not any("trapdoor" in c for c in channel_calls)

        # DM user should receive the private text
        dm_user = ctx.client.fetch_user.return_value
        dm_calls = [c[0][0] for c in dm_user.send.call_args_list]
        assert any("trapdoor" in c for c in dm_calls)

    async def test_whisper_ack_posted_to_channel(self):
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.player_map.get_user_id_by_character = MagicMock(return_value="111")
        ctx.claude_bridge.send = AsyncMock(
            return_value="[PRIVATE:thorin]Secret message.[/PRIVATE]"
        )

        await handle_dm(msg, "anything", ctx)

        channel_calls = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("🤫" in c or "whispers" in c.lower() for c in channel_calls)

    async def test_unknown_character_in_marker_skips_silently(self):
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.player_map.get_user_id_by_character = MagicMock(return_value=None)
        ctx.claude_bridge.send = AsyncMock(
            return_value="[PRIVATE:nobody]Secret.[/PRIVATE]Public text."
        )

        await handle_dm(msg, "anything", ctx)

        # Should not crash; public text still posted
        channel_calls = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("Public text" in c for c in channel_calls)

    async def test_dms_disabled_posts_channel_error(self):
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.player_map.get_user_id_by_character = MagicMock(return_value="111")
        ctx.claude_bridge.send = AsyncMock(
            return_value="[PRIVATE:thorin]Secret.[/PRIVATE]"
        )
        forbidden_response = MagicMock()
        forbidden_response.status = 403
        forbidden_response.reason = "Forbidden"
        dm_user = AsyncMock()
        dm_user.send.side_effect = discord.Forbidden(forbidden_response, "Cannot send")
        ctx.client.fetch_user = AsyncMock(return_value=dm_user)

        await handle_dm(msg, "anything", ctx)

        channel_calls = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("DMs are closed" in c or "enable" in c.lower() for c in channel_calls)


@pytest.mark.asyncio
class TestProcessCommandRouting:
    async def test_process_private_marker_sends_dm_not_channel(self):
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.player_map.get_user_id_by_character = MagicMock(return_value="111")
        ctx.claude_bridge.send = AsyncMock(
            return_value="The party moves on.[PRIVATE:thorin]You notice a trapdoor.[/PRIVATE]"
        )

        await handle_process(msg, "we enter the room", ctx)

        # Channel should NOT contain the private text
        channel_calls = [c[0][0] for c in msg.channel.send.call_args_list]
        assert not any("trapdoor" in c for c in channel_calls)

        # DM user should receive the private text
        dm_user = ctx.client.fetch_user.return_value
        dm_calls = [c[0][0] for c in dm_user.send.call_args_list]
        assert any("trapdoor" in c for c in dm_calls)

    async def test_process_unknown_character_skips_silently(self):
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.player_map.get_user_id_by_character = MagicMock(return_value=None)
        ctx.claude_bridge.send = AsyncMock(
            return_value="[PRIVATE:nobody]Secret.[/PRIVATE]Public text."
        )

        await handle_process(msg, "anything", ctx)

        # Should not crash; public text still posted
        channel_calls = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("Public text" in c for c in channel_calls)
