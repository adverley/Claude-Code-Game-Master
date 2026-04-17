"""Tests for discord_bot.private_chat."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from discord_bot.private_chat import PrivateChatManager


class TestPrivateChatState:
    def test_no_active_chat_by_default(self):
        mgr = PrivateChatManager()
        assert mgr.is_active("12345") is False
        assert mgr.get_active_chats() == {}

    def test_start_chat(self):
        mgr = PrivateChatManager()
        mgr.start_chat("12345", character="Thorin", discord_name="Player1")
        assert mgr.is_active("12345") is True

    def test_end_chat(self):
        mgr = PrivateChatManager()
        mgr.start_chat("12345", character="Thorin", discord_name="Player1")
        mgr.end_chat("12345")
        assert mgr.is_active("12345") is False

    def test_end_chat_when_not_active(self):
        mgr = PrivateChatManager()
        mgr.end_chat("12345")
        assert mgr.is_active("12345") is False

    def test_get_active_chats(self):
        mgr = PrivateChatManager()
        mgr.start_chat("111", character="Thorin", discord_name="Player1")
        mgr.start_chat("222", character="Gandalf", discord_name="Player2")
        active = mgr.get_active_chats()
        assert len(active) == 2
        assert active["111"].character == "Thorin"
        assert active["222"].character == "Gandalf"

    def test_message_count_increments(self):
        mgr = PrivateChatManager()
        mgr.start_chat("111", character="Thorin", discord_name="Player1")
        assert mgr.get_active_chats()["111"].message_count == 0
        mgr.increment_message_count("111")
        mgr.increment_message_count("111")
        assert mgr.get_active_chats()["111"].message_count == 2


class TestPromptBuilding:
    def test_build_first_message_prompt(self):
        mgr = PrivateChatManager()
        prompt = mgr.build_prompt(
            character="Thorin",
            discord_name="Player1",
            message_content="Can I sneak past the guard?",
            is_first_message=True,
        )
        assert "[PRIVATE CONVERSATION with Thorin (Player1)]" in prompt
        assert "No spoilers" in prompt
        assert "Do not advance" in prompt
        assert "[PUBLIC]" in prompt
        assert "Thorin says: Can I sneak past the guard?" in prompt
        assert "[/PRIVATE CONVERSATION]" in prompt

    def test_build_continuation_prompt(self):
        mgr = PrivateChatManager()
        prompt = mgr.build_prompt(
            character="Thorin",
            discord_name="Player1",
            message_content="I offer him 50 gold.",
            is_first_message=False,
        )
        assert "[PRIVATE CONVERSATION with Thorin continues]" in prompt
        assert "Thorin says: I offer him 50 gold." in prompt
        assert "No spoilers" not in prompt
        assert "[/PRIVATE CONVERSATION]" in prompt

    def test_build_done_prompt(self):
        mgr = PrivateChatManager()
        prompt = mgr.build_done_prompt(character="Thorin")
        assert "[PRIVATE CONVERSATION with Thorin" in prompt
        assert "ENDING" in prompt
        assert "[PUBLIC]...[/PUBLIC]" in prompt
        assert "[/PRIVATE CONVERSATION]" in prompt

    def test_build_process_note(self):
        mgr = PrivateChatManager()
        mgr.start_chat("111", character="Thorin", discord_name="Player1")
        mgr.start_chat("222", character="Gandalf", discord_name="Player2")
        note = mgr.build_process_notes()
        assert "Thorin" in note
        assert "Gandalf" in note
        assert "private conversation" in note

    def test_build_process_note_empty_when_no_chats(self):
        mgr = PrivateChatManager()
        assert mgr.build_process_notes() == ""

    def test_build_lite_prompt(self):
        mgr = PrivateChatManager()
        character_json = '{"name": "Thorin", "class": "Fighter", "level": 5}'
        campaign_info = "Campaign: Test, Location: Tavern"
        prompt = mgr.build_lite_prompt(
            character="Thorin",
            message_content="What spells do I have?",
            character_json=character_json,
            campaign_info=campaign_info,
        )
        assert "Thorin" in prompt
        assert character_json in prompt
        assert campaign_info in prompt
        assert "What spells do I have?" in prompt
        assert "No plot advancement" in prompt


def _make_ctx(*, session_active=True, character="Thorin", discord_name="Player1",
              user_id="12345", claude_response="DM response."):
    """Build a minimal mock BotContext."""
    ctx = MagicMock()
    ctx.player_map.get_character.return_value = character
    ctx.player_map.get_discord_name.return_value = discord_name
    ctx.claude_bridge.is_active = session_active
    ctx.claude_bridge.send = AsyncMock(return_value=claude_response)
    ctx.claude_bridge.send_oneshot = AsyncMock(return_value=claude_response)
    ctx.main_channel = AsyncMock()
    ctx.config = {}
    ctx.campaign_dir = Path("world-state/campaigns/test-campaign")
    ctx.claude_bridge._project_dir = "/fake/dir"
    return ctx


def _make_message(content, user_id="12345"):
    """Build a minimal mock Discord DM message."""
    msg = AsyncMock()
    msg.content = content
    msg.author.id = int(user_id)
    msg.author.bot = False
    msg.channel.send = AsyncMock()
    return msg


class TestHandleDmMessage:
    @pytest.mark.asyncio
    async def test_unregistered_player(self):
        mgr = PrivateChatManager()
        ctx = _make_ctx()
        ctx.player_map.get_character.return_value = None
        msg = _make_message("Hello DM")

        await mgr.handle_dm_message(msg, ctx)
        msg.channel.send.assert_called_once()
        call_text = msg.channel.send.call_args[0][0]
        assert "join" in call_text.lower()

    @pytest.mark.asyncio
    async def test_starts_new_chat(self):
        mgr = PrivateChatManager()
        ctx = _make_ctx()
        msg = _make_message("Can I sneak past?")

        await mgr.handle_dm_message(msg, ctx)
        assert mgr.is_active("12345")
        ctx.main_channel.send.assert_called()
        channel_text = ctx.main_channel.send.call_args[0][0]
        assert "Thorin" in channel_text
        msg.channel.send.assert_called()

    @pytest.mark.asyncio
    async def test_continues_existing_chat(self):
        mgr = PrivateChatManager()
        ctx = _make_ctx()
        msg1 = _make_message("First message")
        msg2 = _make_message("Follow up")

        await mgr.handle_dm_message(msg1, ctx)
        await mgr.handle_dm_message(msg2, ctx)

        assert mgr.get_active_chats()["12345"].message_count == 2
        assert ctx.claude_bridge.send.call_count == 2

    @pytest.mark.asyncio
    async def test_done_ends_chat(self):
        mgr = PrivateChatManager()
        ctx = _make_ctx(claude_response="Farewell.\n[PUBLIC]The NPC calms down.[/PUBLIC]")
        msg_start = _make_message("I want to bribe the guard")
        msg_done = _make_message("!done")

        await mgr.handle_dm_message(msg_start, ctx)
        await mgr.handle_dm_message(msg_done, ctx)

        assert not mgr.is_active("12345")
        channel_calls = [c[0][0] for c in ctx.main_channel.send.call_args_list]
        joined = " ".join(channel_calls)
        assert "NPC calms down" in joined

    @pytest.mark.asyncio
    async def test_done_when_not_active(self):
        mgr = PrivateChatManager()
        ctx = _make_ctx()
        msg = _make_message("!done")

        await mgr.handle_dm_message(msg, ctx)
        msg.channel.send.assert_called_once()
        call_text = msg.channel.send.call_args[0][0]
        assert "no active" in call_text.lower() or "don't have" in call_text.lower()

    @pytest.mark.asyncio
    async def test_lite_mode_no_session(self):
        mgr = PrivateChatManager()
        ctx = _make_ctx(session_active=False, claude_response="You have 3 spell slots.")
        msg = _make_message("What spells do I have?")

        with patch("discord_bot.private_chat._load_lite_context", return_value=("char json", "campaign info")):
            await mgr.handle_dm_message(msg, ctx)

        assert not mgr.is_active("12345")
        ctx.claude_bridge.send_oneshot.assert_called_once()
        ctx.claude_bridge.send.assert_not_called()
        # Should have sent at least the lite-mode notice
        assert msg.channel.send.call_count >= 1


    @pytest.mark.asyncio
    async def test_response_wrapped_in_private_marker_still_delivered(self):
        """Claude often wraps DM responses in [PRIVATE:character] — player must still receive them."""
        mgr = PrivateChatManager()
        ctx = _make_ctx(claude_response="[PRIVATE:Thorin]Secret lore about your backstory.[/PRIVATE]")
        msg = _make_message("Tell me something nobody knows about Thorin")

        await mgr.handle_dm_message(msg, ctx)

        # The player should receive the whisper content even though public is empty
        dm_calls = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("Secret lore" in text for text in dm_calls)

    @pytest.mark.asyncio
    async def test_done_response_wrapped_in_private_marker_still_delivered(self):
        """Claude may wrap !done response in [PRIVATE:character] — player must still receive it."""
        mgr = PrivateChatManager()
        ctx = _make_ctx(claude_response="[PRIVATE:Thorin]The deal is done.[/PRIVATE]\n[PUBLIC]The NPC nods.[/PUBLIC]")
        msg_start = _make_message("I bribe the guard")
        msg_done = _make_message("!done")

        await mgr.handle_dm_message(msg_start, ctx)
        await mgr.handle_dm_message(msg_done, ctx)

        dm_calls = [c[0][0] for c in msg_done.channel.send.call_args_list]
        assert any("deal is done" in text for text in dm_calls)


class TestFullFlow:
    @pytest.mark.asyncio
    async def test_full_flow_start_chat_exchange_done(self):
        """Integration test: start -> exchange -> !done with [PUBLIC] output."""
        mgr = PrivateChatManager()

        ctx = _make_ctx()
        responses = [
            "Interesting. What do you offer the guard?",
            "The guard considers your offer. He seems interested.",
            "Good luck.\n[PUBLIC]The guard steps aside and opens the gate.[/PUBLIC]",
        ]
        ctx.claude_bridge.send = AsyncMock(side_effect=responses)

        msg1 = _make_message("I want to bribe the guard")
        msg2 = _make_message("I offer 50 gold")
        msg_done = _make_message("!done")

        # Start chat
        await mgr.handle_dm_message(msg1, ctx)
        assert mgr.is_active("12345")
        ctx.main_channel.send.assert_called_with("*Thorin pulls the DM aside for a private word...*")
        assert "What do you offer" in msg1.channel.send.call_args[0][0]

        # Continue chat
        await mgr.handle_dm_message(msg2, ctx)
        assert mgr.get_active_chats()["12345"].message_count == 2

        # End chat
        ctx.main_channel.send.reset_mock()
        await mgr.handle_dm_message(msg_done, ctx)
        assert not mgr.is_active("12345")

        # Verify channel received: return notification + [PUBLIC] content
        channel_calls = [c[0][0] for c in ctx.main_channel.send.call_args_list]
        assert channel_calls[0] == "*Thorin returns to the group.*"
        assert "guard steps aside" in channel_calls[1]

        # Verify player received the private wrap-up
        done_dm_text = msg_done.channel.send.call_args[0][0]
        assert "Good luck" in done_dm_text
