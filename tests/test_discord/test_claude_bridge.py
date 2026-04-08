import pytest
from discord_bot.claude_bridge import ClaudeBridge


class TestClaudeBridge:
    def test_initial_state_no_session(self):
        bridge = ClaudeBridge(project_dir="/fake/path")
        assert bridge.session_id is None
        assert bridge.is_active is False

    def test_start_session_generates_id(self):
        bridge = ClaudeBridge(project_dir="/fake/path")
        session_id = bridge.start_session("lost-mines")
        assert session_id is not None
        assert session_id.startswith("discord-lost-mines-")
        assert bridge.is_active is True

    def test_end_session_clears_state(self):
        bridge = ClaudeBridge(project_dir="/fake/path")
        bridge.start_session("lost-mines")
        bridge.end_session()
        assert bridge.session_id is None
        assert bridge.is_active is False

    def test_build_command_includes_session_id(self):
        bridge = ClaudeBridge(project_dir="/fake/path")
        bridge.start_session("test")
        cmd = bridge._build_command("Hello DM")
        assert "--print" in cmd
        assert "--session-id" in cmd
        assert bridge.session_id in cmd

    def test_build_command_raises_when_no_session(self):
        bridge = ClaudeBridge(project_dir="/fake/path")
        with pytest.raises(RuntimeError, match="No active session"):
            bridge._build_command("test")

    def test_build_init_prompt(self):
        bridge = ClaudeBridge(project_dir="/fake/path")
        players = {
            "111": {"discord_name": "Erik", "character": "thorin"},
            "222": {"discord_name": "Sara", "character": "elara"},
        }
        prompt = bridge._build_init_prompt("lost-mines", players)
        assert "lost-mines" in prompt
        assert "Erik" in prompt
        assert "thorin" in prompt
        assert ".claude/commands/dm.md" in prompt
        assert "CONTINUE CAMPAIGN" in prompt
