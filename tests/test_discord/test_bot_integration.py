import pytest
from unittest.mock import AsyncMock, MagicMock
from discord_bot.bot import BotContext, on_message_handler


class FakeDiscordMessage:
    def __init__(self, content, user_id="111", display_name="Erik", is_bot=False, channel_id="999"):
        self.content = content
        self.author = MagicMock()
        self.author.id = user_id
        self.author.display_name = display_name
        self.author.bot = is_bot
        self.channel = MagicMock()
        self.channel.id = int(channel_id)
        self.channel.send = AsyncMock()


def make_ctx(channel_id=999):
    ctx = MagicMock(spec=BotContext)
    ctx.channel_id = channel_id
    ctx.player_map = MagicMock()
    ctx.player_map.get_character.return_value = "thorin"
    ctx.player_map.get_discord_name.return_value = "Erik"
    ctx.message_buffer = MagicMock()
    ctx.activity_tracker = MagicMock()
    return ctx


class TestOnMessageHandler:
    def test_ignores_bot_messages(self):
        ctx = make_ctx()
        msg = FakeDiscordMessage("!dm hello", is_bot=True)

        result = on_message_handler(msg, ctx)
        assert result == "ignored"

    def test_ignores_wrong_channel(self):
        ctx = make_ctx(channel_id=999)
        msg = FakeDiscordMessage("!dm hello", channel_id="888")

        result = on_message_handler(msg, ctx)
        assert result == "ignored"

    def test_tracks_non_command_messages(self):
        ctx = make_ctx()
        msg = FakeDiscordMessage("just chatting", channel_id="999")

        result = on_message_handler(msg, ctx)
        assert result == "tracked"
        ctx.message_buffer.add.assert_called_once()

    def test_routes_command_messages(self):
        ctx = make_ctx()
        msg = FakeDiscordMessage("!help", channel_id="999")

        result = on_message_handler(msg, ctx)
        assert result == "command"

    def test_commands_not_added_to_buffer(self):
        ctx = make_ctx()
        msg = FakeDiscordMessage("!dm I search", channel_id="999")

        on_message_handler(msg, ctx)
        ctx.message_buffer.add.assert_not_called()


class TestActivityRecording:
    def test_records_activity_for_registered_player_chat(self):
        ctx = make_ctx()
        ctx.activity_tracker = MagicMock()
        ctx.player_map.get_character.return_value = "thorin"
        msg = FakeDiscordMessage("hello world", channel_id="999")

        on_message_handler(msg, ctx)

        ctx.activity_tracker.record.assert_called_once_with("111")

    def test_records_activity_for_registered_player_command(self):
        ctx = make_ctx()
        ctx.activity_tracker = MagicMock()
        ctx.player_map.get_character.return_value = "thorin"
        msg = FakeDiscordMessage("!help", channel_id="999")

        on_message_handler(msg, ctx)

        ctx.activity_tracker.record.assert_called_once_with("111")

    def test_does_not_record_for_unregistered_player(self):
        ctx = make_ctx()
        ctx.activity_tracker = MagicMock()
        ctx.player_map.get_character.return_value = None
        msg = FakeDiscordMessage("hello", channel_id="999")

        on_message_handler(msg, ctx)

        ctx.activity_tracker.record.assert_not_called()
