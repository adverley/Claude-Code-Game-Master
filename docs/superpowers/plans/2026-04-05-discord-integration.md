# Discord Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Discord bot that lets a group of friends play D&D with Claude as DM, piping messages into a persistent Claude Code CLI session.

**Architecture:** A `discord.py` bot running locally tracks all channel messages in a rolling buffer. Mechanical commands (`!roll`, `!inventory`, `!status`) call `lib/` Python directly. Narrative commands (`!dm`) pipe the message delta into a persistent `claude --session-id` session. A `player-map.json` maps Discord users to character files in a `characters/` directory.

**Tech Stack:** Python 3.11+, `discord.py`, Claude Code CLI (`claude --print --session-id`), existing `lib/` managers.

---

## File Structure

```
discord-bot/
├── bot.py                  # Entry point — discord.py client, event loop, command dispatch
├── config.py               # Load and validate config.json
├── config.json             # Bot token, channel ID, campaign (gitignored)
├── config.example.json     # Template for config.json
├── message_buffer.py       # Rolling message buffer with delta extraction
├── claude_bridge.py        # Spawn claude CLI subprocess, manage session lifecycle
├── player_map.py           # Read/write player-map.json, resolve Discord user → character
├── commands/
│   ├── __init__.py         # Command registry and dispatch
│   ├── dm.py               # !dm — narrative trigger via claude_bridge
│   ├── roll.py             # !roll — calls lib/dice.py directly
│   ├── inventory.py        # !inventory — calls lib/player_manager.py directly
│   ├── status.py           # !status — calls lib/player_manager.py directly
│   ├── session.py          # !session-start, !session-end
│   └── join.py             # !join — player registration
├── requirements.txt        # discord.py
tests/
└── test_discord/
    ├── test_message_buffer.py
    ├── test_player_map.py
    ├── test_config.py
    ├── test_claude_bridge.py
    ├── test_commands.py
    └── test_bot_integration.py
```

**Existing files modified:**
- `.gitignore` — add `discord-bot/config.json`
- `pyproject.toml` — add `discord` optional dependency group

---

### Task 1: Project Scaffolding & Config

**Files:**
- Create: `discord-bot/config.example.json`
- Create: `discord-bot/config.py`
- Create: `discord-bot/requirements.txt`
- Create: `tests/test_discord/test_config.py`
- Modify: `.gitignore`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write the config test**

```python
# tests/test_discord/test_config.py
import json
import pytest
from pathlib import Path


def write_config(tmp_path, data):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data))
    return config_path


class TestLoadConfig:
    def test_loads_valid_config(self, tmp_path):
        from discord_bot.config import load_config

        path = write_config(tmp_path, {
            "bot_token": "test-token-123",
            "channel_id": "999888777",
            "campaign": "lost-mines",
        })
        cfg = load_config(path)
        assert cfg["bot_token"] == "test-token-123"
        assert cfg["channel_id"] == "999888777"
        assert cfg["campaign"] == "lost-mines"
        assert cfg["message_buffer_size"] == 50  # default

    def test_missing_required_field_raises(self, tmp_path):
        from discord_bot.config import load_config

        path = write_config(tmp_path, {
            "bot_token": "test-token-123",
            # missing channel_id and campaign
        })
        with pytest.raises(ValueError, match="channel_id"):
            load_config(path)

    def test_custom_buffer_size(self, tmp_path):
        from discord_bot.config import load_config

        path = write_config(tmp_path, {
            "bot_token": "tok",
            "channel_id": "123",
            "campaign": "test",
            "message_buffer_size": 100,
        })
        cfg = load_config(path)
        assert cfg["message_buffer_size"] == 100

    def test_missing_file_raises(self, tmp_path):
        from discord_bot.config import load_config

        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.json")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_discord/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'discord_bot'`

- [ ] **Step 3: Create config module**

```python
# discord-bot/config.py
"""Load and validate bot configuration."""

import json
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = ["bot_token", "channel_id", "campaign"]
DEFAULTS = {
    "message_buffer_size": 50,
}


def load_config(path: Path) -> dict[str, Any]:
    """Load config from JSON file, validate required fields, apply defaults."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for field in REQUIRED_FIELDS:
        if field not in data:
            raise ValueError(f"Missing required config field: {field}")

    for key, default in DEFAULTS.items():
        data.setdefault(key, default)

    return data
```

- [ ] **Step 4: Create config.example.json**

```json
{
  "bot_token": "YOUR_BOT_TOKEN_HERE",
  "channel_id": "YOUR_CHANNEL_ID_HERE",
  "campaign": "YOUR_CAMPAIGN_NAME",
  "message_buffer_size": 50
}
```

- [ ] **Step 5: Create requirements.txt**

```
discord.py>=2.3.0
```

- [ ] **Step 6: Update .gitignore**

Add this line:
```
discord-bot/config.json
```

- [ ] **Step 7: Update pyproject.toml**

Add to `[project.optional-dependencies]`:
```toml
discord = [
    "discord.py>=2.3.0",
]
```

And update the `full` group to include `discord`:
```toml
full = [
    "dm-claude[voice]",
    "dm-claude[rag]",
    "dm-claude[discord]",
]
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_discord/test_config.py -v`
Expected: 4 passed

Note: Tests import from `discord_bot.config`. Add `discord-bot` to Python path — create `tests/test_discord/__init__.py` and add `sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "discord-bot"))` in a `conftest.py`, or configure `pyproject.toml` to include `discord-bot` as a package source. Simplest: create `tests/test_discord/conftest.py`:

```python
# tests/test_discord/conftest.py
import sys
from pathlib import Path

# Add discord-bot to import path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "discord-bot"))
```

- [ ] **Step 9: Commit**

```bash
git add discord-bot/config.py discord-bot/config.example.json discord-bot/requirements.txt tests/test_discord/ .gitignore pyproject.toml
git commit -m "feat(discord): add project scaffolding and config loader"
```

---

### Task 2: Message Buffer

**Files:**
- Create: `discord-bot/message_buffer.py`
- Create: `tests/test_discord/test_message_buffer.py`

- [ ] **Step 1: Write the message buffer tests**

```python
# tests/test_discord/test_message_buffer.py
import time
from discord_bot.message_buffer import MessageBuffer


class TestMessageBuffer:
    def test_add_and_get_all(self):
        buf = MessageBuffer(max_size=5)
        buf.add("Erik", "Thorin", "I don't trust this merchant", is_command=False)
        buf.add("Sara", "Elara", "agreed", is_command=False)

        messages = buf.get_all()
        assert len(messages) == 2
        assert messages[0]["discord_name"] == "Erik"
        assert messages[0]["character_name"] == "Thorin"
        assert messages[0]["content"] == "I don't trust this merchant"
        assert messages[0]["is_command"] is False

    def test_rolling_window_evicts_oldest(self):
        buf = MessageBuffer(max_size=3)
        buf.add("A", "CharA", "msg1", is_command=False)
        buf.add("B", "CharB", "msg2", is_command=False)
        buf.add("C", "CharC", "msg3", is_command=False)
        buf.add("D", "CharD", "msg4", is_command=False)

        messages = buf.get_all()
        assert len(messages) == 3
        assert messages[0]["discord_name"] == "B"  # oldest surviving

    def test_get_delta_returns_new_messages(self):
        buf = MessageBuffer(max_size=50)
        buf.add("Erik", "Thorin", "hello", is_command=False)
        buf.add("Sara", "Elara", "hi", is_command=False)

        buf.mark_sent()  # mark current position

        buf.add("Erik", "Thorin", "I search the room", is_command=True)
        buf.add("Tom", "Gandalf", "me too", is_command=False)

        delta = buf.get_delta()
        assert len(delta) == 2
        assert delta[0]["content"] == "I search the room"

    def test_get_delta_empty_when_nothing_new(self):
        buf = MessageBuffer(max_size=50)
        buf.add("Erik", "Thorin", "hello", is_command=False)
        buf.mark_sent()

        delta = buf.get_delta()
        assert len(delta) == 0

    def test_format_delta_for_claude(self):
        buf = MessageBuffer(max_size=50)
        buf.add("Erik", "Thorin", "let's be careful", is_command=False)
        buf.add("Sara", "Elara", "!dm I search the room", is_command=True)

        delta = buf.get_delta()
        formatted = buf.format_for_claude(delta, active_player="Erik", active_character="Thorin", command_text="I search the room")

        assert "Erik (playing Thorin)" in formatted
        assert "Sara (playing Elara)" in formatted
        assert "Active player: Erik (Thorin)" in formatted
        assert "Command: I search the room" in formatted

    def test_add_stores_timestamp(self):
        buf = MessageBuffer(max_size=5)
        buf.add("Erik", "Thorin", "test", is_command=False)
        msg = buf.get_all()[0]
        assert "timestamp" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_discord/test_message_buffer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'discord_bot'`

- [ ] **Step 3: Implement message buffer**

```python
# discord-bot/message_buffer.py
"""Rolling message buffer that tracks Discord channel messages."""

from collections import deque
from datetime import datetime, timezone
from typing import Optional


class MessageBuffer:
    def __init__(self, max_size: int = 50):
        self._messages: deque[dict] = deque(maxlen=max_size)
        self._sent_index: int = 0  # index into _messages marking last sent position

    def add(self, discord_name: str, character_name: str, content: str, *, is_command: bool) -> None:
        """Add a message to the buffer."""
        self._messages.append({
            "discord_name": discord_name,
            "character_name": character_name,
            "content": content,
            "is_command": is_command,
            "timestamp": datetime.now(timezone.utc).strftime("%H:%M"),
        })

    def get_all(self) -> list[dict]:
        """Return all messages in the buffer."""
        return list(self._messages)

    def get_delta(self) -> list[dict]:
        """Return messages added since the last mark_sent() call."""
        all_msgs = list(self._messages)
        return all_msgs[self._sent_index:]

    def mark_sent(self) -> None:
        """Mark current position — future get_delta() calls return only newer messages."""
        self._sent_index = len(self._messages)

    def format_for_claude(
        self,
        messages: list[dict],
        *,
        active_player: str,
        active_character: str,
        command_text: str,
    ) -> str:
        """Format a list of messages into the context block sent to Claude."""
        lines = ["[Discord context since last DM response]"]
        for msg in messages:
            lines.append(
                f"[{msg['timestamp']}] {msg['discord_name']} (playing {msg['character_name']}): {msg['content']}"
            )
        lines.append("")
        lines.append(f"Active player: {active_player} ({active_character})")
        lines.append(f"Command: {command_text}")
        return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_discord/test_message_buffer.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add discord-bot/message_buffer.py tests/test_discord/test_message_buffer.py
git commit -m "feat(discord): add rolling message buffer with delta tracking"
```

---

### Task 3: Player Map

**Files:**
- Create: `discord-bot/player_map.py`
- Create: `tests/test_discord/test_player_map.py`

- [ ] **Step 1: Write player map tests**

```python
# tests/test_discord/test_player_map.py
import json
import pytest
from pathlib import Path
from discord_bot.player_map import PlayerMap


def make_player_map_file(tmp_path, data=None):
    path = tmp_path / "player-map.json"
    if data is not None:
        path.write_text(json.dumps(data))
    return path


class TestPlayerMap:
    def test_load_existing_file(self, tmp_path):
        path = make_player_map_file(tmp_path, {
            "players": {
                "111": {"discord_name": "Erik", "character": "thorin"}
            }
        })
        pm = PlayerMap(path)
        assert pm.get_character("111") == "thorin"
        assert pm.get_discord_name("111") == "Erik"

    def test_missing_user_returns_none(self, tmp_path):
        path = make_player_map_file(tmp_path, {"players": {}})
        pm = PlayerMap(path)
        assert pm.get_character("999") is None
        assert pm.get_discord_name("999") is None

    def test_join_adds_player(self, tmp_path):
        path = make_player_map_file(tmp_path, {"players": {}})
        pm = PlayerMap(path)
        pm.join("222", "Sara", "elara")

        assert pm.get_character("222") == "elara"
        assert pm.get_discord_name("222") == "Sara"

        # Verify persisted to disk
        reloaded = json.loads(path.read_text())
        assert reloaded["players"]["222"]["character"] == "elara"

    def test_join_overwrites_existing(self, tmp_path):
        path = make_player_map_file(tmp_path, {
            "players": {"111": {"discord_name": "Erik", "character": "thorin"}}
        })
        pm = PlayerMap(path)
        pm.join("111", "Erik", "gandalf")
        assert pm.get_character("111") == "gandalf"

    def test_creates_file_if_missing(self, tmp_path):
        path = tmp_path / "player-map.json"
        pm = PlayerMap(path)
        pm.join("111", "Erik", "thorin")
        assert path.exists()
        assert pm.get_character("111") == "thorin"

    def test_get_all_players(self, tmp_path):
        path = make_player_map_file(tmp_path, {
            "players": {
                "111": {"discord_name": "Erik", "character": "thorin"},
                "222": {"discord_name": "Sara", "character": "elara"},
            }
        })
        pm = PlayerMap(path)
        players = pm.get_all()
        assert len(players) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_discord/test_player_map.py -v`
Expected: FAIL

- [ ] **Step 3: Implement player map**

```python
# discord-bot/player_map.py
"""Maps Discord user IDs to campaign characters."""

import json
from pathlib import Path
from typing import Optional


class PlayerMap:
    def __init__(self, path: Path):
        self._path = Path(path)
        self._data: dict = {"players": {}}
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)

    def _save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def get_character(self, user_id: str) -> Optional[str]:
        """Get character name for a Discord user ID."""
        player = self._data["players"].get(user_id)
        return player["character"] if player else None

    def get_discord_name(self, user_id: str) -> Optional[str]:
        """Get Discord display name for a user ID."""
        player = self._data["players"].get(user_id)
        return player["discord_name"] if player else None

    def join(self, user_id: str, discord_name: str, character: str) -> None:
        """Register or update a player's character mapping."""
        self._data["players"][user_id] = {
            "discord_name": discord_name,
            "character": character,
        }
        self._save()

    def get_all(self) -> dict[str, dict]:
        """Return all player mappings."""
        return dict(self._data["players"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_discord/test_player_map.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add discord-bot/player_map.py tests/test_discord/test_player_map.py
git commit -m "feat(discord): add player map for Discord user to character mapping"
```

---

### Task 4: Claude Bridge (Session Manager)

**Files:**
- Create: `discord-bot/claude_bridge.py`
- Create: `tests/test_discord/test_claude_bridge.py`

- [ ] **Step 1: Write claude bridge tests**

```python
# tests/test_discord/test_claude_bridge.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path
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
        assert "Discord multi-player" in prompt
        assert "Erik" in prompt
        assert "Thorin" in prompt or "thorin" in prompt
        assert "lost-mines" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_discord/test_claude_bridge.py -v`
Expected: FAIL

- [ ] **Step 3: Implement claude bridge**

```python
# discord-bot/claude_bridge.py
"""Manages the Claude Code CLI subprocess and session lifecycle."""

import asyncio
import time
from pathlib import Path
from typing import Optional


class ClaudeBridge:
    def __init__(self, project_dir: str):
        self._project_dir = Path(project_dir)
        self.session_id: Optional[str] = None
        self._lock = asyncio.Lock()

    @property
    def is_active(self) -> bool:
        return self.session_id is not None

    def start_session(self, campaign: str) -> str:
        """Start a new Claude Code session. Returns the session ID."""
        timestamp = int(time.time())
        self.session_id = f"discord-{campaign}-{timestamp}"
        return self.session_id

    def end_session(self) -> None:
        """End the current session."""
        self.session_id = None

    def _build_command(self, prompt: str) -> list[str]:
        """Build the claude CLI command list."""
        if not self.is_active:
            raise RuntimeError("No active session. Run !session-start first.")
        return [
            "claude",
            "--print",
            "--session-id", self.session_id,
            prompt,
        ]

    def _build_init_prompt(self, campaign: str, players: dict[str, dict]) -> str:
        """Build the initialization prompt for a new session."""
        player_lines = []
        for uid, info in players.items():
            player_lines.append(f"- {info['discord_name']} plays {info['character']}")
        player_block = "\n".join(player_lines) if player_lines else "- No players registered yet"

        return (
            f"You are the DM for a Discord multi-player D&D session.\n"
            f"Campaign: {campaign}\n\n"
            f"Players:\n{player_block}\n\n"
            f"Each player has their own character file in characters/.\n"
            f"When a player acts, use their character for rolls and state changes.\n"
            f"You can update any character as needed (e.g. area damage hits everyone).\n\n"
            f"Start by running:\n"
            f"  bash tools/dm-session.sh start\n"
            f"  bash tools/dm-session.sh context\n\n"
            f"Then narrate the opening scene based on where the campaign left off.\n"
            f"Respond in character as the DM. Be vivid and engaging."
        )

    async def send(self, prompt: str, timeout: float = 120.0) -> str:
        """Send a prompt to the Claude session and return the response."""
        async with self._lock:
            cmd = self._build_command(prompt)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._project_dir),
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                raise TimeoutError(f"Claude did not respond within {timeout}s")

            if proc.returncode != 0:
                error_msg = stderr.decode().strip() if stderr else "Unknown error"
                raise RuntimeError(f"Claude exited with code {proc.returncode}: {error_msg}")

            return stdout.decode().strip()

    async def send_init(self, campaign: str, players: dict[str, dict], timeout: float = 180.0) -> str:
        """Initialize a new session with the DM prompt."""
        prompt = self._build_init_prompt(campaign, players)
        return await self.send(prompt, timeout=timeout)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_discord/test_claude_bridge.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add discord-bot/claude_bridge.py tests/test_discord/test_claude_bridge.py
git commit -m "feat(discord): add Claude bridge for CLI session management"
```

---

### Task 5: Command Registry & Dispatch

**Files:**
- Create: `discord-bot/commands/__init__.py`
- Create: `tests/test_discord/test_commands.py`

- [ ] **Step 1: Write command registry tests**

```python
# tests/test_discord/test_commands.py
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
        expected = {"dm", "roll", "inventory", "status", "session-start", "session-end", "join", "help"}
        assert set(COMMANDS.keys()) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_discord/test_commands.py -v`
Expected: FAIL

- [ ] **Step 3: Implement command registry**

```python
# discord-bot/commands/__init__.py
"""Command registry and parser for Discord bot commands."""

from typing import Optional

# Registry of known commands — handlers are added by each command module
COMMANDS: dict[str, object] = {}


def register(name: str):
    """Decorator to register a command handler function."""
    def decorator(func):
        COMMANDS[name] = func
        return func
    return decorator


def parse_command(content: str) -> Optional[tuple[str, str]]:
    """Parse a Discord message into (command_name, args) or None if not a command."""
    if not content.startswith("!"):
        return None

    parts = content[1:].split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if cmd not in COMMANDS:
        return None

    return cmd, args


# Import command modules to trigger registration
from discord_bot.commands import dm, roll, inventory, status, session, join, help_cmd  # noqa: E402, F401
```

Note: This import line at the bottom will fail until we create the individual command modules. We'll create stubs now and implement handlers in the next tasks.

Create stub files for all command modules:

```python
# discord-bot/commands/dm.py
from discord_bot.commands import register

@register("dm")
async def handle_dm(message, args, ctx):
    """Handle !dm command — narrative trigger."""
    pass  # Implemented in Task 6
```

```python
# discord-bot/commands/roll.py
from discord_bot.commands import register

@register("roll")
async def handle_roll(message, args, ctx):
    """Handle !roll command — dice rolling."""
    pass  # Implemented in Task 7
```

```python
# discord-bot/commands/inventory.py
from discord_bot.commands import register

@register("inventory")
async def handle_inventory(message, args, ctx):
    """Handle !inventory command."""
    pass  # Implemented in Task 7
```

```python
# discord-bot/commands/status.py
from discord_bot.commands import register

@register("status")
async def handle_status(message, args, ctx):
    """Handle !status command."""
    pass  # Implemented in Task 7
```

```python
# discord-bot/commands/session.py
from discord_bot.commands import register

@register("session-start")
async def handle_session_start(message, args, ctx):
    """Handle !session-start command."""
    pass  # Implemented in Task 8

@register("session-end")
async def handle_session_end(message, args, ctx):
    """Handle !session-end command."""
    pass  # Implemented in Task 8
```

```python
# discord-bot/commands/join.py
from discord_bot.commands import register

@register("join")
async def handle_join(message, args, ctx):
    """Handle !join command."""
    pass  # Implemented in Task 7
```

```python
# discord-bot/commands/help_cmd.py
from discord_bot.commands import register

@register("help")
async def handle_help(message, args, ctx):
    """Handle !help command."""
    pass  # Implemented in Task 7
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_discord/test_commands.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add discord-bot/commands/ tests/test_discord/test_commands.py
git commit -m "feat(discord): add command registry with parse and dispatch"
```

---

### Task 6: !dm Command (Narrative Trigger)

**Files:**
- Modify: `discord-bot/commands/dm.py`
- Create: `tests/test_discord/test_dm_command.py`

- [ ] **Step 1: Write dm command tests**

```python
# tests/test_discord/test_dm_command.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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
        msg.channel.send.assert_called()
        # Response should contain Claude's reply
        sent_text = msg.channel.send.call_args[0][0]
        assert "hidden door" in sent_text

    async def test_rejects_unregistered_player(self):
        msg = FakeMessage()
        ctx = FakeCtx(character=None)

        await handle_dm(msg, "I search", ctx)

        ctx.claude_bridge.send.assert_not_called()
        msg.channel.send.assert_called()
        sent_text = msg.channel.send.call_args[0][0]
        assert "!join" in sent_text

    async def test_rejects_when_no_session(self):
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.claude_bridge.is_active = False

        await handle_dm(msg, "I search", ctx)

        ctx.claude_bridge.send.assert_not_called()
        msg.channel.send.assert_called()
        sent_text = msg.channel.send.call_args[0][0]
        assert "session-start" in sent_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_discord/test_dm_command.py -v`
Expected: FAIL (handle_dm is a stub)

Note: You need `pytest-asyncio` for async tests. Add to dev dependencies or install: `uv add --dev pytest-asyncio`

- [ ] **Step 3: Implement !dm command**

```python
# discord-bot/commands/dm.py
"""!dm command — sends narrative prompt to Claude via the bridge."""

from discord_bot.commands import register

DISCORD_MSG_LIMIT = 2000


@register("dm")
async def handle_dm(message, args: str, ctx) -> None:
    """Handle !dm <text> — pipe message context + command to Claude."""
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id)

    if character is None:
        await message.channel.send("You're not registered. Use `!join <character_name>` first.")
        return

    if not ctx.claude_bridge.is_active:
        await message.channel.send("No active session. Use `!session-start` first.")
        return

    discord_name = ctx.player_map.get_discord_name(user_id)
    delta = ctx.message_buffer.get_delta()
    formatted = ctx.message_buffer.format_for_claude(
        delta,
        active_player=discord_name,
        active_character=character,
        command_text=args,
    )

    # Send "thinking" indicator
    thinking_msg = await message.channel.send("*The DM is thinking...*")

    try:
        response = await ctx.claude_bridge.send(formatted)
        await thinking_msg.delete()
        # Split long responses to respect Discord's 2000 char limit
        for i in range(0, len(response), DISCORD_MSG_LIMIT):
            await message.channel.send(response[i:i + DISCORD_MSG_LIMIT])
    except TimeoutError:
        await thinking_msg.delete()
        await message.channel.send("The DM took too long to respond. Try again or `!session-start` to restart.")
    except RuntimeError as e:
        await thinking_msg.delete()
        await message.channel.send(f"DM error: {e}")
    finally:
        ctx.message_buffer.mark_sent()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_discord/test_dm_command.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add discord-bot/commands/dm.py tests/test_discord/test_dm_command.py
git commit -m "feat(discord): implement !dm narrative command with Claude bridge"
```

---

### Task 7: Mechanical Commands (!roll, !inventory, !status, !join, !help)

**Files:**
- Modify: `discord-bot/commands/roll.py`
- Modify: `discord-bot/commands/inventory.py`
- Modify: `discord-bot/commands/status.py`
- Modify: `discord-bot/commands/join.py`
- Modify: `discord-bot/commands/help_cmd.py`
- Create: `tests/test_discord/test_mechanical_commands.py`

- [ ] **Step 1: Write mechanical command tests**

```python
# tests/test_discord/test_mechanical_commands.py
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# Ensure lib/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))

from discord_bot.commands.roll import handle_roll
from discord_bot.commands.inventory import handle_inventory
from discord_bot.commands.status import handle_status
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
        self.config = {"campaign": "test-campaign"}


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
        assert "Usage" in sent or "usage" in sent.lower() or "!join" in sent


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_discord/test_mechanical_commands.py -v`
Expected: FAIL (handlers are stubs)

- [ ] **Step 3: Implement !roll**

```python
# discord-bot/commands/roll.py
"""!roll command — dice rolling via lib/dice.py."""

import sys
from pathlib import Path
from discord_bot.commands import register

# Add lib/ to path for dice import
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from dice import roll_detailed, DiceRoller

_roller = DiceRoller()


@register("roll")
async def handle_roll(message, args: str, ctx) -> None:
    """Handle !roll <notation> — roll dice and post result."""
    if not args.strip():
        await message.channel.send("Usage: `!roll <dice>` (e.g. `!roll 1d20+5`, `!roll 3d6`)")
        return

    try:
        result = roll_detailed(args.strip())
        # Format without terminal color codes
        rolls_str = ", ".join(str(r) for r in result["rolls"])
        text = f"**{message.author.display_name}** rolls `{result['notation']}`: [{rolls_str}]"

        if result.get("modifier", 0) != 0:
            text += f" {result['modifier']:+d}"

        text += f" = **{result['total']}**"

        if result.get("natural_20"):
            text += " :crossed_swords: **CRITICAL HIT!**"
        elif result.get("natural_1"):
            text += " :skull: **CRITICAL MISS!**"

        await message.channel.send(text)
    except ValueError as e:
        await message.channel.send(f"Invalid dice notation: {e}")
```

- [ ] **Step 4: Implement !inventory**

```python
# discord-bot/commands/inventory.py
"""!inventory command — show player's inventory via lib/player_manager.py."""

import sys
from pathlib import Path
from discord_bot.commands import register

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from player_manager import PlayerManager


@register("inventory")
async def handle_inventory(message, args: str, ctx) -> None:
    """Handle !inventory — show the requesting player's equipment."""
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id)

    if character is None:
        await message.channel.send("You're not registered. Use `!join <character_name>` first.")
        return

    try:
        mgr = PlayerManager(f"world-state", require_active_campaign=True)
        char_data = mgr.get_player(character)
        if not char_data:
            await message.channel.send(f"Character '{character}' not found in campaign.")
            return

        equipment = char_data.get("equipment", [])
        name = char_data.get("name", character)

        if equipment:
            items = "\n".join(f"  {i}. {item}" for i, item in enumerate(equipment, 1))
            await message.channel.send(f"**{name}'s Inventory:**\n{items}")
        else:
            await message.channel.send(f"**{name}'s Inventory:** (empty)")
    except RuntimeError as e:
        await message.channel.send(f"Error: {e}")
```

- [ ] **Step 5: Implement !status**

```python
# discord-bot/commands/status.py
"""!status command — show player's character status."""

import sys
from pathlib import Path
from discord_bot.commands import register

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from player_manager import PlayerManager


@register("status")
async def handle_status(message, args: str, ctx) -> None:
    """Handle !status — show the requesting player's character summary."""
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id)

    if character is None:
        await message.channel.send("You're not registered. Use `!join <character_name>` first.")
        return

    try:
        mgr = PlayerManager(f"world-state", require_active_campaign=True)
        summary = mgr.show_player(character)
        if summary:
            await message.channel.send(f"**{summary}**")
        else:
            await message.channel.send(f"Character '{character}' not found.")
    except RuntimeError as e:
        await message.channel.send(f"Error: {e}")
```

- [ ] **Step 6: Implement !join**

```python
# discord-bot/commands/join.py
"""!join command — register a Discord user to a character."""

from discord_bot.commands import register


@register("join")
async def handle_join(message, args: str, ctx) -> None:
    """Handle !join <character_name> — link Discord user to a character."""
    character_name = args.strip()
    if not character_name:
        await message.channel.send("Usage: `!join <character_name>` (e.g. `!join thorin`)")
        return

    user_id = str(message.author.id)
    discord_name = message.author.display_name
    ctx.player_map.join(user_id, discord_name, character_name)

    await message.channel.send(f"**{discord_name}** is now playing **{character_name}**.")
```

- [ ] **Step 7: Implement !help**

```python
# discord-bot/commands/help_cmd.py
"""!help command — show available commands."""

from discord_bot.commands import register

HELP_TEXT = """**D&D Discord Bot Commands:**

**Gameplay:**
`!dm <action>` — Tell the DM what you do (triggers narrative response)
`!roll <dice>` — Roll dice (e.g. `!roll 1d20+5`, `!roll 3d6`)

**Character:**
`!inventory` — Show your character's equipment
`!status` — Show your character summary (HP, level, gold)
`!join <character>` — Link your Discord account to a character

**Session:**
`!session-start` — Start a new DM session
`!session-end [summary]` — End the current session

`!help` — Show this message
"""


@register("help")
async def handle_help(message, args: str, ctx) -> None:
    """Handle !help — list available commands."""
    await message.channel.send(HELP_TEXT)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_discord/test_mechanical_commands.py -v`
Expected: 5 passed

- [ ] **Step 9: Commit**

```bash
git add discord-bot/commands/ tests/test_discord/test_mechanical_commands.py
git commit -m "feat(discord): implement mechanical commands (roll, inventory, status, join, help)"
```

---

### Task 8: Session Commands (!session-start, !session-end)

**Files:**
- Modify: `discord-bot/commands/session.py`
- Create: `tests/test_discord/test_session_commands.py`

- [ ] **Step 1: Write session command tests**

```python
# tests/test_discord/test_session_commands.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from discord_bot.commands.session import handle_session_start, handle_session_end


class FakeMessage:
    def __init__(self):
        self.author = MagicMock()
        self.author.display_name = "Erik"
        self.channel = MagicMock()
        self.channel.send = AsyncMock()


class FakeCtx:
    def __init__(self, active=False):
        self.claude_bridge = MagicMock()
        self.claude_bridge.is_active = active
        self.claude_bridge.start_session = MagicMock(return_value="discord-test-123")
        self.claude_bridge.send_init = AsyncMock(return_value="Welcome adventurers! You stand at the entrance of a dark cave.")
        self.claude_bridge.send = AsyncMock(return_value="Session ended. The party rests for the night.")
        self.claude_bridge.end_session = MagicMock()
        self.player_map = MagicMock()
        self.player_map.get_all.return_value = {
            "111": {"discord_name": "Erik", "character": "thorin"}
        }
        self.config = {"campaign": "test-campaign"}


@pytest.mark.asyncio
class TestSessionStart:
    async def test_starts_session_and_posts_narration(self):
        msg = FakeMessage()
        ctx = FakeCtx(active=False)

        await handle_session_start(msg, "", ctx)

        ctx.claude_bridge.start_session.assert_called_once_with("test-campaign")
        ctx.claude_bridge.send_init.assert_called_once()
        # Should post the opening narration
        calls = msg.channel.send.call_args_list
        assert any("Welcome" in str(c) or "adventurers" in str(c) for c in calls)

    async def test_rejects_if_session_already_active(self):
        msg = FakeMessage()
        ctx = FakeCtx(active=True)

        await handle_session_start(msg, "", ctx)

        ctx.claude_bridge.start_session.assert_not_called()
        sent = msg.channel.send.call_args[0][0]
        assert "already" in sent.lower()


@pytest.mark.asyncio
class TestSessionEnd:
    async def test_ends_session_and_posts_summary(self):
        msg = FakeMessage()
        ctx = FakeCtx(active=True)

        await handle_session_end(msg, "We defeated the goblins", ctx)

        ctx.claude_bridge.send.assert_called_once()
        ctx.claude_bridge.end_session.assert_called_once()

    async def test_rejects_if_no_active_session(self):
        msg = FakeMessage()
        ctx = FakeCtx(active=False)

        await handle_session_end(msg, "", ctx)

        ctx.claude_bridge.send.assert_not_called()
        sent = msg.channel.send.call_args[0][0]
        assert "no active session" in sent.lower() or "session-start" in sent.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_discord/test_session_commands.py -v`
Expected: FAIL

- [ ] **Step 3: Implement session commands**

```python
# discord-bot/commands/session.py
"""!session-start and !session-end commands."""

from discord_bot.commands import register

DISCORD_MSG_LIMIT = 2000


@register("session-start")
async def handle_session_start(message, args: str, ctx) -> None:
    """Start a new Claude DM session."""
    if ctx.claude_bridge.is_active:
        await message.channel.send("A session is already active. Use `!session-end` first.")
        return

    campaign = ctx.config["campaign"]
    await message.channel.send(f"*Starting DM session for **{campaign}**...*")

    ctx.claude_bridge.start_session(campaign)
    players = ctx.player_map.get_all()

    try:
        response = await ctx.claude_bridge.send_init(campaign, players)
        for i in range(0, len(response), DISCORD_MSG_LIMIT):
            await message.channel.send(response[i:i + DISCORD_MSG_LIMIT])
    except (TimeoutError, RuntimeError) as e:
        ctx.claude_bridge.end_session()
        await message.channel.send(f"Failed to start session: {e}")


@register("session-end")
async def handle_session_end(message, args: str, ctx) -> None:
    """End the current DM session."""
    if not ctx.claude_bridge.is_active:
        await message.channel.send("No active session. Use `!session-start` first.")
        return

    summary = args.strip() if args.strip() else "Session ended by player request."
    await message.channel.send("*Ending session...*")

    try:
        prompt = f"The session is ending. Summary: {summary}\nPlease wrap up the narrative and run: bash tools/dm-session.sh end \"{summary}\""
        response = await ctx.claude_bridge.send(prompt)
        for i in range(0, len(response), DISCORD_MSG_LIMIT):
            await message.channel.send(response[i:i + DISCORD_MSG_LIMIT])
    except (TimeoutError, RuntimeError) as e:
        await message.channel.send(f"Error during session end: {e}")
    finally:
        ctx.claude_bridge.end_session()
        await message.channel.send("*Session ended.*")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_discord/test_session_commands.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add discord-bot/commands/session.py tests/test_discord/test_session_commands.py
git commit -m "feat(discord): implement session-start and session-end commands"
```

---

### Task 9: Bot Main Entry Point

**Files:**
- Create: `discord-bot/bot.py`
- Create: `tests/test_discord/test_bot_integration.py`

- [ ] **Step 1: Write bot integration tests**

```python
# tests/test_discord/test_bot_integration.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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


class TestOnMessageHandler:
    def test_ignores_bot_messages(self):
        ctx = MagicMock()
        ctx.channel_id = 999
        msg = FakeDiscordMessage("!dm hello", is_bot=True)

        # Should return without processing
        result = on_message_handler(msg, ctx)
        assert result == "ignored"

    def test_ignores_wrong_channel(self):
        ctx = MagicMock()
        ctx.channel_id = 999
        msg = FakeDiscordMessage("!dm hello", channel_id="888")

        result = on_message_handler(msg, ctx)
        assert result == "ignored"

    def test_tracks_non_command_messages(self):
        ctx = MagicMock()
        ctx.channel_id = 999
        ctx.player_map.get_character.return_value = "thorin"
        ctx.player_map.get_discord_name.return_value = "Erik"
        msg = FakeDiscordMessage("just chatting", channel_id="999")

        result = on_message_handler(msg, ctx)
        assert result == "tracked"
        ctx.message_buffer.add.assert_called_once()

    def test_routes_command_messages(self):
        ctx = MagicMock()
        ctx.channel_id = 999
        ctx.player_map.get_character.return_value = "thorin"
        ctx.player_map.get_discord_name.return_value = "Erik"
        msg = FakeDiscordMessage("!help", channel_id="999")

        result = on_message_handler(msg, ctx)
        assert result == "command"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_discord/test_bot_integration.py -v`
Expected: FAIL

- [ ] **Step 3: Implement bot.py**

```python
# discord-bot/bot.py
"""Discord bot entry point — connects to Discord, tracks messages, dispatches commands."""

import asyncio
import sys
from pathlib import Path
from dataclasses import dataclass

import discord

from discord_bot.config import load_config
from discord_bot.message_buffer import MessageBuffer
from discord_bot.claude_bridge import ClaudeBridge
from discord_bot.player_map import PlayerMap
from discord_bot.commands import parse_command, COMMANDS

PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


@dataclass
class BotContext:
    """Shared state passed to all command handlers."""
    config: dict
    message_buffer: MessageBuffer
    claude_bridge: ClaudeBridge
    player_map: PlayerMap
    channel_id: int


def on_message_handler(message, ctx: BotContext) -> str:
    """
    Synchronous message pre-processing. Returns:
    - "ignored" if the message should be skipped
    - "tracked" if it was a non-command message (added to buffer)
    - "command" if it's a command that needs async dispatch
    """
    # Ignore bot messages
    if message.author.bot:
        return "ignored"

    # Ignore messages from other channels
    if message.channel.id != ctx.channel_id:
        return "ignored"

    # Look up player info for buffer tracking
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id) or "unregistered"
    discord_name = ctx.player_map.get_discord_name(user_id) or message.author.display_name

    # Track all messages in buffer
    parsed = parse_command(message.content)
    ctx.message_buffer.add(
        discord_name=discord_name,
        character_name=character,
        content=message.content,
        is_command=parsed is not None,
    )

    if parsed is not None:
        return "command"

    return "tracked"


async def dispatch_command(message, ctx: BotContext) -> None:
    """Parse and dispatch a command message."""
    parsed = parse_command(message.content)
    if parsed is None:
        return

    cmd_name, args = parsed
    handler = COMMANDS.get(cmd_name)
    if handler:
        await handler(message, args, ctx)


def main():
    """Run the Discord bot."""
    config = load_config(CONFIG_PATH)

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    campaign_dir = PROJECT_DIR / "world-state" / "campaigns" / config["campaign"]
    player_map_path = campaign_dir / "player-map.json"

    ctx = BotContext(
        config=config,
        message_buffer=MessageBuffer(max_size=config["message_buffer_size"]),
        claude_bridge=ClaudeBridge(project_dir=str(PROJECT_DIR)),
        player_map=PlayerMap(player_map_path),
        channel_id=int(config["channel_id"]),
    )

    @client.event
    async def on_ready():
        print(f"Bot connected as {client.user}")
        print(f"Listening in channel: {ctx.channel_id}")
        print(f"Campaign: {config['campaign']}")

    @client.event
    async def on_message(message):
        result = on_message_handler(message, ctx)
        if result == "command":
            await dispatch_command(message, ctx)

    client.run(config["bot_token"])


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_discord/test_bot_integration.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add discord-bot/bot.py tests/test_discord/test_bot_integration.py
git commit -m "feat(discord): add bot entry point with message tracking and command dispatch"
```

---

### Task 10: Multi-Character Support in PlayerManager

**Files:**
- Modify: `lib/player_manager.py`
- Modify: `tests/test_player_manager.py`

This task adds support for a `characters/` directory alongside the existing `character.json` so Claude can manage multiple player characters during a Discord session.

- [ ] **Step 1: Write test for characters/ directory loading**

Add to `tests/test_player_manager.py`:

```python
def make_multi_character_campaign(tmp_path):
    """Campaign with characters/ directory instead of character.json."""
    campaign_dir = tmp_path / "world-state" / "campaigns" / "test-campaign"
    campaign_dir.mkdir(parents=True)
    ws = tmp_path / "world-state"
    (ws / "active-campaign.txt").write_text("test-campaign")

    overview = {
        "campaign_name": "Test Campaign",
        "time_of_day": "Day",
        "current_date": "Day 1",
    }
    (campaign_dir / "campaign-overview.json").write_text(
        json.dumps(overview, ensure_ascii=False)
    )

    chars_dir = campaign_dir / "characters"
    chars_dir.mkdir()

    thorin = {
        "name": "Thorin",
        "level": 3,
        "hp": {"current": 30, "max": 35},
        "gold": 200,
        "xp": 1000,
        "equipment": ["Warhammer", "Shield"],
    }
    (chars_dir / "thorin.json").write_text(json.dumps(thorin, ensure_ascii=False))

    elara = {
        "name": "Elara",
        "level": 3,
        "hp": {"current": 22, "max": 22},
        "gold": 150,
        "xp": 900,
        "equipment": ["Longbow", "Arrows"],
    }
    (chars_dir / "elara.json").write_text(json.dumps(elara, ensure_ascii=False))

    return str(ws), campaign_dir


class TestMultiCharacter:
    def test_load_character_from_characters_dir(self, tmp_path):
        ws, camp = make_multi_character_campaign(tmp_path)
        mgr = PlayerManager(ws)
        char = mgr.get_player("thorin")
        assert char is not None
        assert char["name"] == "Thorin"
        assert char["level"] == 3

    def test_list_players_from_characters_dir(self, tmp_path):
        ws, camp = make_multi_character_campaign(tmp_path)
        mgr = PlayerManager(ws)
        players = mgr.list_players()
        assert "thorin" in players
        assert "elara" in players

    def test_modify_hp_multi_character(self, tmp_path):
        ws, camp = make_multi_character_campaign(tmp_path)
        mgr = PlayerManager(ws)
        result = mgr.modify_hp("thorin", -10)
        assert result["success"] is True
        assert result["current_hp"] == 20

        # Elara should be unaffected
        elara = mgr.get_player("elara")
        assert elara["hp"]["current"] == 22

    def test_show_all_players_multi(self, tmp_path):
        ws, camp = make_multi_character_campaign(tmp_path)
        mgr = PlayerManager(ws)
        summaries = mgr.show_all_players()
        assert len(summaries) == 2

    def test_single_character_json_still_works(self, tmp_path):
        """Existing single character.json campaigns must keep working."""
        ws, camp = make_campaign(tmp_path)
        mgr = PlayerManager(ws)
        char = mgr.get_player("Hero")
        assert char is not None
        assert char["name"] == "Hero"
```

- [ ] **Step 2: Run tests to verify failures**

Run: `uv run pytest tests/test_player_manager.py::TestMultiCharacter -v`
Expected: Some tests fail — the current `PlayerManager` has a `characters/` (legacy) directory path but the lookup logic prioritizes `character.json`. When `character.json` doesn't exist AND `characters/` does, it should use that directory. Currently the `_is_using_single_character` check gates this — we need to ensure `_load_character` and `_get_character_path` correctly fall through to the `characters/` directory.

- [ ] **Step 3: Update PlayerManager to support characters/ directory**

The existing code already has `self.characters_dir` and the legacy path logic. The key change: when there's no `character.json` but `characters/` exists, use it. The current code should mostly work — verify and fix:

In `player_manager.py`, the `_load_character` method already has the fallback path. The issue is `_get_character_path` — it needs to handle the case where `character.json` doesn't exist. Update:

```python
# In _is_using_single_character:
def _is_using_single_character(self) -> bool:
    """Check if we're using the new single character.json format"""
    return self.character_file.exists()
```

This is already correct — if `character.json` exists, use it. If not, fall through to `characters/` directory. The existing logic should work. Run tests to confirm. If `list_players` or `show_all_players` don't scan `characters/` correctly when `character.json` is absent, fix those methods.

The `list_players` and `show_all_players` methods already scan `self.characters_dir` when `_is_using_single_character()` returns False. So the multi-character tests should pass with the existing code.

- [ ] **Step 4: Run all player manager tests**

Run: `uv run pytest tests/test_player_manager.py -v`
Expected: All tests pass (both single-character and multi-character)

- [ ] **Step 5: Commit (only if changes were needed)**

```bash
git add lib/player_manager.py tests/test_player_manager.py
git commit -m "feat: add multi-character campaign tests, verify characters/ directory support"
```

---

### Task 11: Full Integration Test & Documentation

**Files:**
- Create: `discord-bot/README.md`
- Modify: `tests/test_discord/test_bot_integration.py` (add end-to-end test)

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass — both existing tests and new discord tests

- [ ] **Step 2: Create bot README**

```markdown
# Discord Bot for D&D DM

A Discord bot that lets your group play D&D with Claude as DM.

## Setup

### 1. Create a Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application", name it (e.g. "DM Bot")
3. Go to "Bot" tab, click "Reset Token", copy the token
4. Enable **Message Content Intent** under "Privileged Gateway Intents"
5. Go to "OAuth2" > "URL Generator":
   - Scopes: `bot`
   - Permissions: Read Messages/View Channels, Send Messages, Read Message History
6. Copy the generated URL and open it to invite the bot to your server

### 2. Configure the Bot

```bash
cd discord-bot
cp config.example.json config.json
```

Edit `config.json`:
- `bot_token`: Your bot token from step 1
- `channel_id`: Right-click your Discord channel > Copy Channel ID (enable Developer Mode in Discord settings first)
- `campaign`: Name of your campaign folder in `world-state/campaigns/`

### 3. Install Dependencies

```bash
uv pip install discord.py
```

### 4. Run the Bot

```bash
cd discord-bot
uv run python bot.py
```

## Commands

| Command | Description |
|---------|-------------|
| `!dm <action>` | Tell the DM what you do |
| `!roll <dice>` | Roll dice (e.g. `1d20+5`) |
| `!inventory` | Show your equipment |
| `!status` | Show your character summary |
| `!join <character>` | Link your Discord account to a character |
| `!session-start` | Start a DM session |
| `!session-end [summary]` | End the current session |
| `!help` | Show commands |

## How It Works

1. Start with `!session-start` — this launches a persistent Claude Code session
2. Everyone chats normally in the channel — the bot tracks all messages for context
3. When someone wants the DM to act, they use `!dm <what they do>`
4. Claude receives the recent chat context and responds as DM
5. Mechanical commands (`!roll`, `!inventory`, `!status`) are instant — no Claude needed
6. End with `!session-end` when you're done playing
```

- [ ] **Step 3: Commit**

```bash
git add discord-bot/README.md tests/
git commit -m "docs(discord): add bot setup guide and finalize integration tests"
```

---

### Task 12: Final Verification

- [ ] **Step 1: Run full test suite one final time**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 2: Verify project structure**

Run: `ls -la discord-bot/` and `ls -la discord-bot/commands/`
Expected: All files present as specified in the file structure

- [ ] **Step 3: Verify .gitignore**

Run: `grep "discord-bot/config.json" .gitignore`
Expected: Line found

- [ ] **Step 4: Final commit if any cleanup needed**

```bash
git add -A
git commit -m "chore(discord): final cleanup and verification"
```
