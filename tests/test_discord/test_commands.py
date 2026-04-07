import pytest
from discord_bot.commands import parse_command, COMMANDS


class TestParseCommand:
    def test_parse_dm_command(self):
        cmd, args = parse_command("!dm I search the room")
        assert cmd == "dm"
        assert args == "I search the room"

    def test_parse_roll_command(self):
        cmd, args = parse_command("!roll 1d20+5")
        assert cmd == "roll"
        assert args == "1d20+5"

    def test_parse_inventory_no_args(self):
        cmd, args = parse_command("!inventory")
        assert cmd == "inventory"
        assert args == ""

    def test_parse_status_no_args(self):
        cmd, args = parse_command("!status")
        assert cmd == "status"
        assert args == ""

    def test_parse_session_start(self):
        cmd, args = parse_command("!session-start")
        assert cmd == "session-start"
        assert args == ""

    def test_parse_session_end_with_summary(self):
        cmd, args = parse_command("!session-end We defeated the dragon")
        assert cmd == "session-end"
        assert args == "We defeated the dragon"

    def test_parse_join(self):
        cmd, args = parse_command("!join thorin")
        assert cmd == "join"
        assert args == "thorin"

    def test_parse_help(self):
        cmd, args = parse_command("!help")
        assert cmd == "help"

    def test_non_command_returns_none(self):
        result = parse_command("just a regular message")
        assert result is None

    def test_unknown_command_returns_none(self):
        result = parse_command("!foobar something")
        assert result is None

    def test_all_commands_registered(self):
        expected = {"dm", "process", "roll", "inventory", "status", "session-start", "session-end", "join", "help", "overview", "save", "restore", "list-saves"}
        assert set(COMMANDS.keys()) == expected
