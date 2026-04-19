import asyncio
import pytest
import discord
from unittest.mock import AsyncMock, MagicMock, patch
from discord_bot.activity_tracker import ActivityTracker, Pace
from discord_bot.commands.dm import handle_dm, handle_process, _maybe_inject_private_prompt, _advance_plot
from discord_bot.private_chat import PrivateChatManager


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
        # _maybe_inject_private_prompt calls get_all(); provide a real dict
        # so it can filter/sample without crashing on MagicMock iteration.
        self.player_map.get_all.return_value = (
            {"111": {"discord_name": discord_name, "character": character}}
            if character else {}
        )
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
        self.private_chat_manager = PrivateChatManager()
        self.activity_tracker = ActivityTracker()
        self.pace = Pace.ACTIVE
        self.pending_gates = set()


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

    async def test_process_multiblock_narration_with_private_whisper(self):
        """Realistic !process response: public narration with an embedded
        multi-paragraph [PRIVATE:Aldric Ironfeld] whisper block separated
        by horizontal rules."""
        msg = FakeMessage()
        ctx = FakeCtx(character="Aldric Ironfeld", discord_name="AndyV")
        ctx.player_map.get_user_id_by_character = MagicMock(return_value="111")
        ctx.claude_bridge.send = AsyncMock(return_value=(
            "The hall is quiet save for the creak of old timber and the "
            "distant sounds of the village stirring below.\n\n"
            "Tybalt is already at the map, muttering to himself about the "
            "tunnel\u2019s apparent depth and the likely geological composition "
            "of the bedrock. Wren sits backwards in one of the Elder\u2019s "
            "chairs, strumming a single absent chord on her lute, over and "
            "over. Daveth stands near the door, still and patient, hand "
            "resting on his holy symbol.\n\n"
            "---\n\n"
            "[PRIVATE:Aldric Ironfeld]\n\n"
            "You were not idle last night.\n\n"
            "You\u2019ve served under enough commanders to know how they hold "
            "a lie \u2014 not a brazen one, but the kind where they give you "
            "what you need to go, and nothing more. Alderman Cora moved "
            "like that. Deliberate. Measured. Her hands had been steady "
            "when she unrolled the map, but she\u2019d known exactly where to "
            "look before the parchment was halfway open. She\u2019d been to "
            "that page before. Many times.\n\n"
            "And she left before anyone could ask about the warning. "
            "*Do not extinguish your lights.* She\u2019d seen that line. She "
            "knows what it means. She chose silence.\n\n"
            "There was something else. When she mentioned the third "
            "landing, her jaw tightened \u2014 just for a moment, the way a "
            "soldier\u2019s does when they name a place where someone didn\u2019t "
            "come back. Not grief. Not fear. The older thing. Guilt "
            "dressed up as duty.\n\n"
            "Cora has sent people down before. Or she\u2019s been down "
            "herself. Either way: whatever\u2019s on the other side of that "
            "warning, she already knows the shape of it.\n\n"
            "She trusts you enough to point the spear. She doesn\u2019t trust "
            "you enough to tell you what you\u2019re hitting.\n\n"
            "Whether that changes what you do next is up to you.\n\n"
            "[/PRIVATE:Aldric Ironfeld]\n\n"
            "---\n\n"
            "The map lies on the table. The morning is burning off fast.\n\n"
            "**What do you do?**"
        ))

        await handle_process(msg, "", ctx)

        channel_calls = [c[0][0] for c in msg.channel.send.call_args_list]
        channel_text = "\n".join(channel_calls)

        # Public narration reaches the channel
        assert "creak of old timber" in channel_text
        assert "What do you do?" in channel_text

        # Private content stays out of the channel
        assert "not idle last night" not in channel_text
        assert "point the spear" not in channel_text

        # Whisper dispatched as DM to the mapped player
        dm_user = ctx.client.fetch_user.return_value
        dm_calls = [c[0][0] for c in dm_user.send.call_args_list]
        dm_text = "\n".join(dm_calls)
        assert "not idle last night" in dm_text
        assert "point the spear" in dm_text

        # Channel acknowledgement posted
        assert any("\U0001f92b" in c and "Aldric Ironfeld" in c for c in channel_calls)

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


class TestMaybeInjectPrivatePrompt:
    def _make_player_map(self, players: dict[str, str]):
        """Build a mock player_map with get_all() returning the given {id: character} map."""
        pm = MagicMock()
        pm.get_all.return_value = {
            uid: {"discord_name": f"Player{uid}", "character": char}
            for uid, char in players.items()
        }
        return pm

    @patch("discord_bot.commands.dm.random")
    def test_injects_when_roll_succeeds(self, mock_random):
        mock_random.random.return_value = 0.0  # always triggers (< 0.2)
        mock_random.choice.side_effect = lambda x: x[0]

        pm = self._make_player_map({"1": "Thorin", "2": "Elara"})
        result = _maybe_inject_private_prompt("base payload", pm, exclude_character="Thorin")

        assert "[PRIVATE:" in result
        # Should pick from candidates excluding active player
        assert "Elara" in result
        assert "base payload" in result

    @patch("discord_bot.commands.dm.random")
    def test_skips_when_roll_fails(self, mock_random):
        mock_random.random.return_value = 0.99  # does not trigger (> 0.2)

        pm = self._make_player_map({"1": "Thorin"})
        result = _maybe_inject_private_prompt("base payload", pm)

        assert result == "base payload"

    @patch("discord_bot.commands.dm.random")
    def test_skips_when_no_players(self, mock_random):
        mock_random.random.return_value = 0.0

        pm = self._make_player_map({})
        result = _maybe_inject_private_prompt("base payload", pm)

        assert result == "base payload"

    @patch("discord_bot.commands.dm.random")
    def test_falls_back_to_active_player_when_only_one(self, mock_random):
        mock_random.random.return_value = 0.0
        mock_random.choice.side_effect = lambda x: x[0]

        pm = self._make_player_map({"1": "Thorin"})
        result = _maybe_inject_private_prompt("base payload", pm, exclude_character="Thorin")

        # Only one player — should fall back to them
        assert "[PRIVATE:Thorin]" in result

    @patch("discord_bot.commands.dm.random")
    def test_excludes_active_character(self, mock_random):
        mock_random.random.return_value = 0.0
        picked = []
        mock_random.choice.side_effect = lambda x: (picked.extend(x), x[0])[1]

        pm = self._make_player_map({"1": "Thorin", "2": "Elara", "3": "Gandalf"})
        _maybe_inject_private_prompt("payload", pm, exclude_character="Thorin")

        # Thorin should not be in the candidates list
        assert "Thorin" not in picked


def _make_reaction(emoji: str, msg_id: int, user_id: str):
    reaction = MagicMock()
    reaction.emoji = emoji
    reaction.message = MagicMock()
    reaction.message.id = msg_id
    user = MagicMock()
    user.id = user_id
    return reaction, user


@pytest.mark.asyncio
class TestAdvancePlot:
    async def test_sends_to_claude_and_posts_response(self):
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.claude_bridge.send = AsyncMock(return_value="The gate swings open.")

        await _advance_plot(msg, "we push the gate", ctx)

        ctx.claude_bridge.send.assert_called_once()
        calls = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("gate" in c for c in calls)

    async def test_marks_buffer_sent(self):
        msg = FakeMessage()
        ctx = FakeCtx()

        await _advance_plot(msg, "anything", ctx)

        ctx.message_buffer.mark_sent.assert_called_once()


@pytest.mark.asyncio
class TestProcessConfirmation:
    async def test_dm_player_guard_blocks_non_dm(self):
        msg = FakeMessage(display_name="RandomPlayer")
        ctx = FakeCtx()
        ctx.config = {"dm_player": "GameMaster"}

        await handle_process(msg, "advance", ctx)

        ctx.claude_bridge.send.assert_not_called()
        text = msg.channel.send.call_args[0][0]
        assert "GameMaster" in text

    async def test_rejects_when_already_pending(self):
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.pending_gates.add("process")

        await handle_process(msg, "anything", ctx)

        ctx.claude_bridge.send.assert_not_called()
        text = msg.channel.send.call_args[0][0]
        assert "pending" in text.lower()

    async def test_all_active_players_confirm_advances_plot(self):
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx()
        ctx.player_map.get_all.return_value = {
            "111": {"discord_name": "Erik", "character": "thorin"},
            "222": {"discord_name": "Player2", "character": "Elara"},
        }
        ctx.activity_tracker.record("222")

        confirm_msg = AsyncMock()
        confirm_msg.id = 999
        msg.channel.send = AsyncMock(return_value=confirm_msg)

        reaction, user = _make_reaction("✅", 999, "222")
        ctx.client.wait_for = AsyncMock(return_value=(reaction, user))

        await handle_process(msg, "we move north", ctx)

        ctx.claude_bridge.send.assert_called_once()
        assert "process" not in ctx.pending_gates

    async def test_deny_aborts_and_posts_message(self):
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx()
        ctx.player_map.get_all.return_value = {
            "111": {"discord_name": "Erik", "character": "thorin"},
            "222": {"discord_name": "Player2", "character": "Elara"},
        }
        ctx.activity_tracker.record("222")

        confirm_msg = AsyncMock()
        confirm_msg.id = 999
        msg.channel.send = AsyncMock(return_value=confirm_msg)

        reaction, user = _make_reaction("❌", 999, "222")
        ctx.client.wait_for = AsyncMock(return_value=(reaction, user))

        await handle_process(msg, "we move north", ctx)

        ctx.claude_bridge.send.assert_not_called()
        assert "process" not in ctx.pending_gates
        texts = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("denied" in t.lower() or "aborted" in t.lower() for t in texts)

    async def test_timeout_proceeds_without_full_confirmation(self):
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx()
        ctx.player_map.get_all.return_value = {
            "111": {"discord_name": "Erik", "character": "thorin"},
            "222": {"discord_name": "Player2", "character": "Elara"},
        }
        ctx.activity_tracker.record("222")

        confirm_msg = AsyncMock()
        confirm_msg.id = 999
        msg.channel.send = AsyncMock(return_value=confirm_msg)

        ctx.client.wait_for = AsyncMock(side_effect=asyncio.TimeoutError)

        await handle_process(msg, "we move north", ctx)

        ctx.claude_bridge.send.assert_called_once()
        assert "process" not in ctx.pending_gates

    async def test_check_closure_filters_correctly(self):
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx()
        ctx.player_map.get_all.return_value = {
            "111": {"discord_name": "Erik", "character": "thorin"},
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
            raise asyncio.TimeoutError

        ctx.client.wait_for = capture_wait_for

        await handle_process(msg, "we move", ctx)

        assert captured_check is not None
        valid_reaction, valid_user = _make_reaction("✅", 999, "222")
        assert captured_check(valid_reaction, valid_user) is True
        wrong_msg, _ = _make_reaction("✅", 888, "222")
        assert captured_check(wrong_msg, valid_user) is False
        _, non_candidate = _make_reaction("✅", 999, "999")
        assert captured_check(valid_reaction, non_candidate) is False
        wrong_emoji, _ = _make_reaction("🎲", 999, "222")
        assert captured_check(wrong_emoji, valid_user) is False

