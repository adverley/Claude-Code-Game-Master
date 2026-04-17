import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from discord_bot.commands.roll import handle_roll
from discord_bot.commands.join import handle_join
from discord_bot.commands.help_cmd import handle_help


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
        self.config = {}
        self.campaign_dir = Path("world-state/campaigns/test-campaign")
        self.campaign_dir = None


@pytest.mark.asyncio
class TestRollCommand:
    async def test_rolls_valid_notation(self):
        msg = FakeMessage()
        ctx = FakeCtx()

        with patch("discord_bot.commands.roll.roll_detailed") as mock_roll:
            mock_roll.return_value = {
                "notation": "1d20",
                "rolls": [15],
                "modifier": 0,
                "total": 15,
                "type": "standard",
            }
            await handle_roll(msg, "1d20", ctx)

        msg.channel.send.assert_called_once()
        sent = msg.channel.send.call_args[0][0]
        assert "15" in sent

    async def test_invalid_notation(self):
        msg = FakeMessage()
        ctx = FakeCtx()

        with patch("discord_bot.commands.roll.roll_detailed", side_effect=ValueError("Invalid")):
            await handle_roll(msg, "bad", ctx)

        sent = msg.channel.send.call_args[0][0]
        assert "Invalid" in sent or "invalid" in sent.lower()


@pytest.mark.asyncio
class TestJoinCommand:
    async def test_join_registers_player(self):
        msg = FakeMessage(user_id="111", display_name="Erik")
        ctx = FakeCtx()
        ctx.player_map.join = MagicMock()

        await handle_join(msg, "thorin", ctx)

        ctx.player_map.join.assert_called_once_with("111", "Erik", "thorin")
        msg.channel.send.assert_called_once()
        sent = msg.channel.send.call_args[0][0]
        assert "thorin" in sent.lower()

    async def test_join_requires_character_name(self):
        msg = FakeMessage()
        ctx = FakeCtx()

        await handle_join(msg, "", ctx)

        msg.channel.send.assert_called_once()
        sent = msg.channel.send.call_args[0][0]
        assert "!join" in sent


@pytest.mark.asyncio
class TestJoinCharacterLock:
    async def test_join_rejects_switch_when_alive(self, tmp_path):
        """Player with a living character cannot switch to another."""
        # Create character file with no "dead" condition
        chars_dir = tmp_path / "characters"
        chars_dir.mkdir()
        import json
        (chars_dir / "thorin.json").write_text(json.dumps({
            "id": "thorin", "name": "Thorin", "conditions": []
        }))

        msg = FakeMessage(user_id="111", display_name="Erik")
        ctx = FakeCtx(character="Thorin")
        ctx.campaign_dir = tmp_path
        ctx.player_map.join = MagicMock()

        await handle_join(msg, "gandalf", ctx)

        ctx.player_map.join.assert_not_called()
        sent = msg.channel.send.call_args[0][0]
        assert "already playing" in sent.lower()

    async def test_join_allows_switch_when_dead(self, tmp_path):
        """Player whose character is dead can switch."""
        chars_dir = tmp_path / "characters"
        chars_dir.mkdir()
        import json
        (chars_dir / "thorin.json").write_text(json.dumps({
            "id": "thorin", "name": "Thorin", "conditions": ["dead"]
        }))

        msg = FakeMessage(user_id="111", display_name="Erik")
        ctx = FakeCtx(character="Thorin")
        ctx.campaign_dir = tmp_path
        ctx.player_map.join = MagicMock()

        await handle_join(msg, "gandalf", ctx)

        ctx.player_map.join.assert_called_once_with("111", "Erik", "gandalf")

    async def test_join_allows_same_character_rejoin(self, tmp_path):
        """Re-joining as the same character is always allowed."""
        chars_dir = tmp_path / "characters"
        chars_dir.mkdir()
        import json
        (chars_dir / "thorin.json").write_text(json.dumps({
            "id": "thorin", "name": "Thorin", "conditions": []
        }))

        msg = FakeMessage(user_id="111", display_name="Erik")
        ctx = FakeCtx(character="Thorin")
        ctx.campaign_dir = tmp_path
        ctx.player_map.join = MagicMock()

        await handle_join(msg, "thorin", ctx)

        ctx.player_map.join.assert_called_once_with("111", "Erik", "thorin")

    async def test_join_allows_first_join(self):
        """First-time join (no existing character) always works."""
        msg = FakeMessage(user_id="111", display_name="Erik")
        ctx = FakeCtx(character=None)
        ctx.player_map.get_character.return_value = None
        ctx.player_map.join = MagicMock()

        await handle_join(msg, "thorin", ctx)

        ctx.player_map.join.assert_called_once_with("111", "Erik", "thorin")

    async def test_join_allows_switch_when_file_missing(self):
        """If character file doesn't exist, allow switch (prevents typo lockout)."""
        msg = FakeMessage(user_id="111", display_name="Erik")
        ctx = FakeCtx(character="typo-name")
        ctx.campaign_dir = Path("/nonexistent/campaign")
        ctx.player_map.join = MagicMock()

        await handle_join(msg, "gandalf", ctx)

        ctx.player_map.join.assert_called_once_with("111", "Erik", "gandalf")


@pytest.mark.asyncio
class TestHelpCommand:
    async def test_help_lists_commands(self):
        msg = FakeMessage()
        ctx = FakeCtx()

        await handle_help(msg, "", ctx)

        msg.channel.send.assert_called_once()
        sent = msg.channel.send.call_args[0][0]
        assert "!dm" in sent
        assert "!roll" in sent
        assert "!inventory" in sent
        assert "!status" in sent
