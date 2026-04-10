"""Tests for discord_bot.private_chat."""

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
