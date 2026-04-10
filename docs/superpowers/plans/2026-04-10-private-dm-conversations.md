# Private DM Conversations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow players to have multi-turn private conversations with the DM bot via Discord DMs, with observable outcomes posted to the main channel.

**Architecture:** A new `PrivateChatManager` class handles per-player state and prompt framing. DMs are detected in `bot.py`'s `on_message` and routed to the manager. All private messages serialize onto the existing `ClaudeBridge` session queue. A `[PUBLIC]` response marker is added to `response_router.py` for surfacing outcomes to the main channel. A `send_oneshot` method on `ClaudeBridge` supports lite-mode (no active session) queries.

**Tech Stack:** Python 3.11+, discord.py, asyncio, pytest

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `discord_bot/private_chat.py` | PrivateChatManager: per-player state, prompt building, DM message handling |
| Create | `tests/test_response_router.py` | Tests for response router including new [PUBLIC] marker |
| Create | `tests/test_private_chat.py` | Tests for PrivateChatManager state and prompt building |
| Create | `tests/test_claude_bridge.py` | Tests for send_oneshot command building |
| Modify | `discord_bot/response_router.py` | Add [PUBLIC] regex, `public_announcements` field on RoutedResponse |
| Modify | `discord_bot/claude_bridge.py` | Add `send_oneshot()` method |
| Modify | `discord_bot/bot.py` | Add DM listener, `main_channel` on BotContext, wire up PrivateChatManager |
| Modify | `discord_bot/commands/dm.py` | Inject active-private-chat notes into `!process` payloads |

---

### Task 1: Response Router — `[PUBLIC]` Marker

**Files:**
- Modify: `discord_bot/response_router.py`
- Create: `tests/test_response_router.py`

- [ ] **Step 1: Write failing tests for [PUBLIC] extraction**

Create `tests/test_response_router.py`:

```python
"""Tests for discord_bot.response_router."""

from discord_bot.response_router import route_response


def test_no_markers():
    routed = route_response("Just some plain text.")
    assert routed.public == "Just some plain text."
    assert routed.whispers == []
    assert routed.public_announcements == []


def test_public_marker_extracted():
    text = (
        "Private reply to player.\n\n"
        "[PUBLIC]The NPC sheathes his blade and joins the party.[/PUBLIC]"
    )
    routed = route_response(text)
    assert routed.public == "Private reply to player."
    assert routed.public_announcements == [
        "The NPC sheathes his blade and joins the party."
    ]


def test_multiple_public_markers():
    text = (
        "Some DM text.\n\n"
        "[PUBLIC]First observable thing.[/PUBLIC]\n"
        "More DM text.\n"
        "[PUBLIC]Second observable thing.[/PUBLIC]"
    )
    routed = route_response(text)
    assert "Some DM text." in routed.public
    assert "More DM text." in routed.public
    assert routed.public_announcements == [
        "First observable thing.",
        "Second observable thing.",
    ]


def test_public_and_private_markers_together():
    text = (
        "Reply to player.\n\n"
        "[PUBLIC]The door opens.[/PUBLIC]\n\n"
        "[PRIVATE:Thorin]You notice a trap.[/PRIVATE]"
    )
    routed = route_response(text)
    assert routed.public == "Reply to player."
    assert routed.public_announcements == ["The door opens."]
    assert routed.whispers == [("Thorin", "You notice a trap.")]


def test_public_marker_with_mental_model():
    text = (
        "[MENTAL MODEL]DM notes here.[/MENTAL MODEL]\n"
        "Visible text.\n"
        "[PUBLIC]Something everyone sees.[/PUBLIC]"
    )
    routed = route_response(text)
    assert "DM notes" not in routed.public
    assert routed.public_announcements == ["Something everyone sees."]


def test_empty_public_marker():
    text = "Reply.\n[PUBLIC][/PUBLIC]"
    routed = route_response(text)
    assert routed.public == "Reply."
    assert routed.public_announcements == []


def test_existing_private_marker_still_works():
    text = "Narration.\n[PRIVATE:Gandalf]Secret info.[/PRIVATE]"
    routed = route_response(text)
    assert routed.public == "Narration."
    assert routed.whispers == [("Gandalf", "Secret info.")]
    assert routed.public_announcements == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_response_router.py -v`
Expected: FAIL — `RoutedResponse` has no `public_announcements` attribute.

- [ ] **Step 3: Implement [PUBLIC] extraction**

In `discord_bot/response_router.py`, add the `_PUBLIC_RE` regex and update `RoutedResponse` and `route_response()`:

```python
"""Parse [PRIVATE:name]...[/PRIVATE], [PUBLIC]...[/PUBLIC], and [MENTAL MODEL]...[/MENTAL MODEL] markers from Claude responses."""

import re
from dataclasses import dataclass, field

_PRIVATE_RE = re.compile(r'\[PRIVATE:([^\]]+)\](.*?)\[/PRIVATE(?::[^\]]+)?\]', re.DOTALL)
_MENTAL_MODEL_RE = re.compile(r'\[MENTAL MODEL\](.*?)\[/MENTAL MODEL\]', re.DOTALL)
_PUBLIC_RE = re.compile(r'\[PUBLIC\](.*?)\[/PUBLIC\]', re.DOTALL)


@dataclass
class RoutedResponse:
    public: str
    whispers: list[tuple[str, str]] = field(default_factory=list)
    public_announcements: list[str] = field(default_factory=list)


def route_response(text: str) -> RoutedResponse:
    """Split a Claude response into public text, per-character whispers, and public announcements.

    Any [PRIVATE:character_name]...[/PRIVATE] blocks are removed from the
    public text and returned as (character_name, content) tuples in whispers.
    Any [PUBLIC]...[/PUBLIC] blocks are removed and returned in public_announcements.
    """
    whispers: list[tuple[str, str]] = []
    public_announcements: list[str] = []

    def _extract_whisper(match: re.Match) -> str:
        character = match.group(1).strip()
        content = match.group(2).strip()
        whispers.append((character, content))
        return ""

    def _extract_public(match: re.Match) -> str:
        content = match.group(1).strip()
        if content:
            public_announcements.append(content)
        return ""

    text = _MENTAL_MODEL_RE.sub("", text)
    text = _PUBLIC_RE.sub(_extract_public, text)
    public = _PRIVATE_RE.sub(_extract_whisper, text).strip()
    return RoutedResponse(public=public, whispers=whispers, public_announcements=public_announcements)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_response_router.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add discord_bot/response_router.py tests/test_response_router.py
git commit -m "feat: add [PUBLIC] marker extraction to response router"
```

---

### Task 2: ClaudeBridge — `send_oneshot` Method

**Files:**
- Modify: `discord_bot/claude_bridge.py`
- Create: `tests/test_claude_bridge.py`

- [ ] **Step 1: Write failing test for send_oneshot command building**

Create `tests/test_claude_bridge.py`:

```python
"""Tests for discord_bot.claude_bridge."""

from discord_bot.claude_bridge import ClaudeBridge


def test_build_oneshot_command_basic():
    bridge = ClaudeBridge(project_dir="/fake/dir")
    cmd = bridge._build_oneshot_command("What spells do I have?")
    assert cmd == ["claude", "--print", "What spells do I have?"]


def test_build_oneshot_command_with_model():
    bridge = ClaudeBridge(project_dir="/fake/dir", model="sonnet")
    cmd = bridge._build_oneshot_command("Question?")
    assert cmd == ["claude", "--print", "--model", "sonnet", "Question?"]


def test_build_oneshot_command_with_debug():
    bridge = ClaudeBridge(project_dir="/fake/dir", claude_debug=True)
    cmd = bridge._build_oneshot_command("Question?")
    assert cmd == ["claude", "--print", "--debug", "Question?"]


def test_build_oneshot_does_not_use_session():
    bridge = ClaudeBridge(project_dir="/fake/dir")
    bridge.start_session("test-campaign")
    cmd = bridge._build_oneshot_command("Question?")
    # Must NOT contain --session-id or --resume
    assert "--session-id" not in cmd
    assert "--resume" not in cmd
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_claude_bridge.py -v`
Expected: FAIL — `ClaudeBridge` has no `_build_oneshot_command` method.

- [ ] **Step 3: Implement send_oneshot**

In `discord_bot/claude_bridge.py`, add two methods after the existing `send` method:

```python
    def _build_oneshot_command(self, prompt: str) -> list[str]:
        """Build a one-shot claude CLI command (no session)."""
        cmd = ["claude", "--print"]
        if self._model:
            cmd += ["--model", self._model]
        if self._claude_debug:
            cmd.append("--debug")
        cmd.append(prompt)
        return cmd

    async def send_oneshot(self, prompt: str, timeout: float = 60.0) -> str:
        """Run a single prompt without a session. For lite-mode queries."""
        cmd = self._build_oneshot_command(prompt)
        log.info("Claude oneshot [timeout=%.0fs]", timeout)
        log.debug("Oneshot command: %s", " ".join(cmd[:-1]))
        log.debug("--- ONESHOT PROMPT START (%d chars) ---\n%s\n--- ONESHOT PROMPT END ---", len(prompt), prompt)

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
            log.error("Claude oneshot timed out after %.0fs", timeout)
            raise TimeoutError(f"Claude did not respond within {timeout}s")

        stderr_text = stderr.decode().strip() if stderr else ""
        if proc.returncode != 0:
            log.error("Claude oneshot exited %d\nstderr: %s", proc.returncode, stderr_text)
            raise RuntimeError(f"Claude exited with code {proc.returncode}: {stderr_text}")

        response = stdout.decode().strip()
        log.info("Claude oneshot responded (%d chars)", len(response))
        log.debug("--- ONESHOT RESPONSE START ---\n%s\n--- ONESHOT RESPONSE END ---", response)
        return response
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_claude_bridge.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add discord_bot/claude_bridge.py tests/test_claude_bridge.py
git commit -m "feat: add send_oneshot to ClaudeBridge for sessionless queries"
```

---

### Task 3: PrivateChatManager — State Management

**Files:**
- Create: `discord_bot/private_chat.py`
- Create: `tests/test_private_chat.py`

- [ ] **Step 1: Write failing tests for state management**

Create `tests/test_private_chat.py`:

```python
"""Tests for discord_bot.private_chat."""

from discord_bot.private_chat import PrivateChatManager


def test_no_active_chat_by_default():
    mgr = PrivateChatManager()
    assert mgr.is_active("12345") is False
    assert mgr.get_active_chats() == {}


def test_start_chat():
    mgr = PrivateChatManager()
    mgr.start_chat("12345", character="Thorin", discord_name="Player1")
    assert mgr.is_active("12345") is True


def test_end_chat():
    mgr = PrivateChatManager()
    mgr.start_chat("12345", character="Thorin", discord_name="Player1")
    mgr.end_chat("12345")
    assert mgr.is_active("12345") is False


def test_end_chat_when_not_active():
    mgr = PrivateChatManager()
    # Should not raise
    mgr.end_chat("12345")
    assert mgr.is_active("12345") is False


def test_get_active_chats():
    mgr = PrivateChatManager()
    mgr.start_chat("111", character="Thorin", discord_name="Player1")
    mgr.start_chat("222", character="Gandalf", discord_name="Player2")
    active = mgr.get_active_chats()
    assert len(active) == 2
    assert active["111"].character == "Thorin"
    assert active["222"].character == "Gandalf"


def test_message_count_increments():
    mgr = PrivateChatManager()
    mgr.start_chat("111", character="Thorin", discord_name="Player1")
    assert mgr.get_active_chats()["111"].message_count == 0
    mgr.increment_message_count("111")
    mgr.increment_message_count("111")
    assert mgr.get_active_chats()["111"].message_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_private_chat.py -v`
Expected: FAIL — module `discord_bot.private_chat` does not exist.

- [ ] **Step 3: Implement PrivateChatManager state management**

Create `discord_bot/private_chat.py`:

```python
"""Manages multi-turn private DM conversations between players and the DM bot."""

import logging
from dataclasses import dataclass

log = logging.getLogger("dm_bot.private_chat")


@dataclass
class PrivateChat:
    character: str
    discord_name: str
    message_count: int = 0


class PrivateChatManager:
    def __init__(self):
        self._chats: dict[str, PrivateChat] = {}

    def is_active(self, user_id: str) -> bool:
        return user_id in self._chats

    def start_chat(self, user_id: str, *, character: str, discord_name: str) -> None:
        self._chats[user_id] = PrivateChat(character=character, discord_name=discord_name)
        log.info("Private chat started: %s (%s)", character, discord_name)

    def end_chat(self, user_id: str) -> None:
        chat = self._chats.pop(user_id, None)
        if chat:
            log.info("Private chat ended: %s (%s), %d messages exchanged",
                     chat.character, chat.discord_name, chat.message_count)

    def get_active_chats(self) -> dict[str, PrivateChat]:
        return dict(self._chats)

    def increment_message_count(self, user_id: str) -> None:
        if user_id in self._chats:
            self._chats[user_id].message_count += 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_private_chat.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add discord_bot/private_chat.py tests/test_private_chat.py
git commit -m "feat: add PrivateChatManager with state tracking"
```

---

### Task 4: PrivateChatManager — Prompt Building

**Files:**
- Modify: `discord_bot/private_chat.py`
- Modify: `tests/test_private_chat.py`

- [ ] **Step 1: Write failing tests for prompt building**

Append to `tests/test_private_chat.py`:

```python
def test_build_first_message_prompt():
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


def test_build_continuation_prompt():
    mgr = PrivateChatManager()
    prompt = mgr.build_prompt(
        character="Thorin",
        discord_name="Player1",
        message_content="I offer him 50 gold.",
        is_first_message=False,
    )
    assert "[PRIVATE CONVERSATION with Thorin continues]" in prompt
    assert "Thorin says: I offer him 50 gold." in prompt
    assert "No spoilers" not in prompt  # Rules only on first message
    assert "[/PRIVATE CONVERSATION]" in prompt


def test_build_done_prompt():
    mgr = PrivateChatManager()
    prompt = mgr.build_done_prompt(character="Thorin")
    assert "[PRIVATE CONVERSATION with Thorin" in prompt
    assert "ENDING" in prompt
    assert "[PUBLIC]...[/PUBLIC]" in prompt
    assert "[/PRIVATE CONVERSATION]" in prompt


def test_build_process_note():
    mgr = PrivateChatManager()
    mgr.start_chat("111", character="Thorin", discord_name="Player1")
    mgr.start_chat("222", character="Gandalf", discord_name="Player2")
    note = mgr.build_process_notes()
    assert "Thorin" in note
    assert "Gandalf" in note
    assert "private conversation" in note


def test_build_process_note_empty_when_no_chats():
    mgr = PrivateChatManager()
    assert mgr.build_process_notes() == ""


def test_build_lite_prompt():
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_private_chat.py -v`
Expected: FAIL — `PrivateChatManager` has no `build_prompt` method.

- [ ] **Step 3: Implement prompt building methods**

Append to the `PrivateChatManager` class in `discord_bot/private_chat.py`:

```python
    def build_prompt(self, *, character: str, discord_name: str,
                     message_content: str, is_first_message: bool) -> str:
        if is_first_message:
            return (
                f"[PRIVATE CONVERSATION with {character} ({discord_name})]\n"
                f"The player has initiated a private conversation with you.\n"
                f"Rules: No spoilers. No changes outside their character. Do not advance\n"
                f"the main plot. The player may propose a secret action — discuss it with\n"
                f"them privately. When the conversation ends, you will be asked to provide\n"
                f"a [PUBLIC] summary of any observable outcomes.\n\n"
                f"{character} says: {message_content}\n"
                f"[/PRIVATE CONVERSATION]"
            )
        return (
            f"[PRIVATE CONVERSATION with {character} continues]\n"
            f"{character} says: {message_content}\n"
            f"[/PRIVATE CONVERSATION]"
        )

    def build_done_prompt(self, *, character: str) -> str:
        return (
            f"[PRIVATE CONVERSATION with {character} — ENDING]\n"
            f"The player is ending the private conversation. Wrap up and include a\n"
            f"[PUBLIC]...[/PUBLIC] block with anything the other players would observe\n"
            f"or notice as a result. If nothing observable happened, the [PUBLIC] block\n"
            f"can be empty or omitted. Frame the [PUBLIC] content however makes\n"
            f"narrative sense — you decide whether to attribute it.\n"
            f"[/PRIVATE CONVERSATION]"
        )

    def build_process_notes(self) -> str:
        if not self._chats:
            return ""
        lines = []
        for chat in self._chats.values():
            lines.append(
                f"[NOTE: {chat.character} is currently in a private conversation with the DM. "
                f"You may hold back on advancing events that would directly involve them, "
                f"or narrate around their temporary absence.]"
            )
        return "\n".join(lines)

    def build_lite_prompt(self, *, character: str, message_content: str,
                          character_json: str, campaign_info: str) -> str:
        return (
            f"You are a D&D Dungeon Master assistant answering a quick question.\n\n"
            f"Campaign context:\n{campaign_info}\n\n"
            f"Character data:\n{character_json}\n\n"
            f"{character} asks: {message_content}\n\n"
            f"Answer mechanics, spells, inventory, and character questions only. "
            f"No plot advancement, no narrative."
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_private_chat.py -v`
Expected: All 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add discord_bot/private_chat.py tests/test_private_chat.py
git commit -m "feat: add prompt building to PrivateChatManager"
```

---

### Task 5: PrivateChatManager — `handle_dm_message` Entry Point

**Files:**
- Modify: `discord_bot/private_chat.py`
- Modify: `tests/test_private_chat.py`

This is the main async method that processes all incoming DMs. It depends on `BotContext`, `ClaudeBridge`, `PlayerMap`, and Discord message objects — so the tests here use lightweight mocks and focus on the routing logic. The prompts and state management are already tested in Tasks 3-4.

- [ ] **Step 1: Write failing tests for handle_dm_message**

Append to `tests/test_private_chat.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from discord_bot.private_chat import PrivateChatManager
from discord_bot.response_router import RoutedResponse


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
    ctx.config = {"campaign": "test-campaign"}
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


def test_handle_dm_unregistered_player():
    mgr = PrivateChatManager()
    ctx = _make_ctx()
    ctx.player_map.get_character.return_value = None
    msg = _make_message("Hello DM")

    asyncio.get_event_loop().run_until_complete(
        mgr.handle_dm_message(msg, ctx)
    )
    msg.channel.send.assert_called_once()
    call_text = msg.channel.send.call_args[0][0]
    assert "don't recognize" in call_text.lower() or "join" in call_text.lower()


def test_handle_dm_starts_new_chat():
    mgr = PrivateChatManager()
    ctx = _make_ctx()
    msg = _make_message("Can I sneak past?")

    asyncio.get_event_loop().run_until_complete(
        mgr.handle_dm_message(msg, ctx)
    )
    assert mgr.is_active("12345")
    # Channel notification
    ctx.main_channel.send.assert_called()
    channel_text = ctx.main_channel.send.call_args[0][0]
    assert "Thorin" in channel_text
    # DM reply sent back to player
    msg.channel.send.assert_called()


def test_handle_dm_continues_existing_chat():
    mgr = PrivateChatManager()
    ctx = _make_ctx()
    msg1 = _make_message("First message")
    msg2 = _make_message("Follow up")

    loop = asyncio.get_event_loop()
    loop.run_until_complete(mgr.handle_dm_message(msg1, ctx))
    loop.run_until_complete(mgr.handle_dm_message(msg2, ctx))

    assert mgr.get_active_chats()["12345"].message_count == 2
    # ClaudeBridge.send called twice (both in-session)
    assert ctx.claude_bridge.send.call_count == 2


def test_handle_dm_done_ends_chat():
    mgr = PrivateChatManager()
    ctx = _make_ctx(claude_response="Farewell.\n[PUBLIC]The NPC calms down.[/PUBLIC]")
    msg_start = _make_message("I want to bribe the guard")
    msg_done = _make_message("!done")

    loop = asyncio.get_event_loop()
    loop.run_until_complete(mgr.handle_dm_message(msg_start, ctx))
    loop.run_until_complete(mgr.handle_dm_message(msg_done, ctx))

    assert not mgr.is_active("12345")
    # Check [PUBLIC] was posted to main channel
    channel_calls = [str(c) for c in ctx.main_channel.send.call_args_list]
    joined = " ".join(channel_calls)
    assert "NPC calms down" in joined


def test_handle_dm_done_when_not_active():
    mgr = PrivateChatManager()
    ctx = _make_ctx()
    msg = _make_message("!done")

    asyncio.get_event_loop().run_until_complete(
        mgr.handle_dm_message(msg, ctx)
    )
    msg.channel.send.assert_called_once()
    call_text = msg.channel.send.call_args[0][0]
    assert "don't have" in call_text.lower() or "no active" in call_text.lower()


def test_handle_dm_lite_mode_no_session():
    mgr = PrivateChatManager()
    ctx = _make_ctx(session_active=False, claude_response="You have 3 spell slots.")
    msg = _make_message("What spells do I have?")

    with patch("discord_bot.private_chat._load_lite_context", return_value=("char json", "campaign info")):
        asyncio.get_event_loop().run_until_complete(
            mgr.handle_dm_message(msg, ctx)
        )

    # Should NOT start a chat
    assert not mgr.is_active("12345")
    # Should use oneshot, not session send
    ctx.claude_bridge.send_oneshot.assert_called_once()
    ctx.claude_bridge.send.assert_not_called()
    # Should reply in DM
    msg.channel.send.assert_called()
    call_text = msg.channel.send.call_args[0][0]
    assert "No active session" in call_text or "spell slots" in call_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_private_chat.py::test_handle_dm_unregistered_player -v`
Expected: FAIL — `PrivateChatManager` has no `handle_dm_message` method.

- [ ] **Step 3: Implement handle_dm_message and lite context loader**

Add the following imports to the top of `discord_bot/private_chat.py`:

```python
import json
from pathlib import Path
from discord_bot.response_router import route_response
```

Add this module-level helper function before the class:

```python
DISCORD_MSG_LIMIT = 2000


def _load_lite_context(project_dir: str, campaign: str, character: str) -> tuple[str, str]:
    """Load minimal character + campaign data for lite-mode queries."""
    base = Path(project_dir) / "world-state" / "campaigns" / campaign

    # Character JSON
    char_path = base / "characters" / f"{character.lower()}.json"
    if not char_path.exists():
        char_path = base / "character.json"
    character_json = ""
    if char_path.exists():
        character_json = char_path.read_text(encoding="utf-8")

    # Campaign overview (name + location)
    overview_path = base / "campaign-overview.json"
    campaign_info = ""
    if overview_path.exists():
        data = json.loads(overview_path.read_text(encoding="utf-8"))
        parts = [f"Campaign: {data.get('campaign_name', campaign)}"]
        if data.get("current_location"):
            parts.append(f"Current location: {data['current_location']}")
        campaign_info = "\n".join(parts)

    return character_json, campaign_info
```

Add the `handle_dm_message` method to the `PrivateChatManager` class:

```python
    async def handle_dm_message(self, message, ctx) -> None:
        """Main entry point for all Discord DMs from players."""
        user_id = str(message.author.id)
        content = message.content.strip()

        # Check if registered
        character = ctx.player_map.get_character(user_id)
        if character is None:
            await message.channel.send(
                "I don't recognize you. Use `!join <character_name>` in the game channel first."
            )
            return

        discord_name = ctx.player_map.get_discord_name(user_id)

        # Handle !done
        if content.lower() == "!done":
            if not self.is_active(user_id):
                await message.channel.send("You don't have an active private conversation.")
                return
            await self._handle_done(message, ctx, user_id, character, discord_name)
            return

        # No active session — lite mode
        if not ctx.claude_bridge.is_active:
            await self._handle_lite(message, ctx, user_id, character, discord_name, content)
            return

        # Start or continue a private chat
        is_first = not self.is_active(user_id)
        if is_first:
            self.start_chat(user_id, character=character, discord_name=discord_name)
            if ctx.main_channel:
                await ctx.main_channel.send(f"*{character} pulls the DM aside for a private word...*")

        prompt = self.build_prompt(
            character=character,
            discord_name=discord_name,
            message_content=content,
            is_first_message=is_first,
        )

        try:
            response = await ctx.claude_bridge.send(prompt)
            self.increment_message_count(user_id)
            routed = route_response(response)

            # Send DM reply to player
            reply = routed.public
            if reply:
                for i in range(0, len(reply), DISCORD_MSG_LIMIT):
                    await message.channel.send(reply[i:i + DISCORD_MSG_LIMIT])
        except TimeoutError:
            await message.channel.send("The DM took too long to respond. Try sending your message again.")
        except RuntimeError as e:
            log.error("Claude error in private chat for %s: %s", character, e)
            await message.channel.send(f"DM error: {e}")

    async def _handle_done(self, message, ctx, user_id: str,
                           character: str, discord_name: str) -> None:
        """End a private conversation and post [PUBLIC] outcomes to channel."""
        prompt = self.build_done_prompt(character=character)
        try:
            response = await ctx.claude_bridge.send(prompt)
            routed = route_response(response)

            # Send wrap-up DM to player
            if routed.public:
                for i in range(0, len(routed.public), DISCORD_MSG_LIMIT):
                    await message.channel.send(routed.public[i:i + DISCORD_MSG_LIMIT])

            # Post return notification + [PUBLIC] content to channel
            if ctx.main_channel:
                await ctx.main_channel.send(f"*{character} returns to the group.*")
                for announcement in routed.public_announcements:
                    for i in range(0, len(announcement), DISCORD_MSG_LIMIT):
                        await ctx.main_channel.send(announcement[i:i + DISCORD_MSG_LIMIT])
        except TimeoutError:
            await message.channel.send("The DM took too long to respond. Try `!done` again.")
            return  # Don't end chat on timeout — let player retry
        except RuntimeError as e:
            log.error("Claude error on !done for %s: %s", character, e)
            await message.channel.send(f"DM error: {e}")
            return

        self.end_chat(user_id)

    async def _handle_lite(self, message, ctx, user_id: str,
                           character: str, discord_name: str, content: str) -> None:
        """Handle a DM when no session is active (lite mode)."""
        character_json, campaign_info = _load_lite_context(
            str(ctx.claude_bridge._project_dir),
            ctx.config["campaign"],
            character,
        )
        prompt = self.build_lite_prompt(
            character=character,
            message_content=content,
            character_json=character_json,
            campaign_info=campaign_info,
        )
        try:
            response = await ctx.claude_bridge.send_oneshot(prompt)
            await message.channel.send(
                f"*(No active session — I can answer basic mechanics and character questions.)*"
            )
            for i in range(0, len(response), DISCORD_MSG_LIMIT):
                await message.channel.send(response[i:i + DISCORD_MSG_LIMIT])
        except TimeoutError:
            await message.channel.send("The DM took too long to respond. Try again.")
        except RuntimeError as e:
            log.error("Claude lite-mode error for %s: %s", character, e)
            await message.channel.send(f"DM error: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_private_chat.py -v`
Expected: All 18 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add discord_bot/private_chat.py tests/test_private_chat.py
git commit -m "feat: add handle_dm_message with full routing logic"
```

---

### Task 6: Wire Up Bot — DM Listener and BotContext

**Files:**
- Modify: `discord_bot/bot.py`

- [ ] **Step 1: Add imports and update BotContext**

In `discord_bot/bot.py`, add the import at the top with the other imports:

```python
from discord_bot.private_chat import PrivateChatManager
```

Add two fields to the `BotContext` dataclass, after the existing `client` field:

```python
@dataclass
class BotContext:
    """Shared state passed to all command handlers."""
    config: dict
    message_buffer: MessageBuffer
    claude_bridge: ClaudeBridge
    player_map: PlayerMap
    channel_id: int
    client: discord.Client = None
    main_channel: discord.TextChannel = None
    private_chat_manager: PrivateChatManager = None
```

- [ ] **Step 2: Initialize PrivateChatManager in main()**

In the `main()` function, after the `ctx = BotContext(...)` block, add the manager:

```python
    ctx = BotContext(
        config=config,
        message_buffer=MessageBuffer(max_size=config["message_buffer_size"]),
        claude_bridge=ClaudeBridge(project_dir=str(PROJECT_DIR), model=model, claude_debug=args.claude_debug),
        player_map=PlayerMap(player_map_path),
        channel_id=int(config["channel_id"]),
        client=client,
        private_chat_manager=PrivateChatManager(),
    )
```

- [ ] **Step 3: Store main_channel on ready**

In the `on_ready` event handler, add after the existing log lines:

```python
    @client.event
    async def on_ready():
        model_label = model or "Claude Code default"
        log.info("Bot connected as %s", client.user)
        log.info("Listening in channel: %s", ctx.channel_id)
        log.info("Campaign: %s", config["campaign"])
        log.info("Model: %s", model_label)
        log.info("Buffer size: %s messages", config["message_buffer_size"])
        ctx.main_channel = client.get_channel(ctx.channel_id)
        if ctx.main_channel is None:
            log.warning("Could not find main channel %s — public notifications will be skipped", ctx.channel_id)
```

- [ ] **Step 4: Add DM listener to on_message**

Replace the `on_message` event handler:

```python
    @client.event
    async def on_message(message):
        if message.author.bot:
            return
        # DMs — no guild means direct message
        if message.guild is None:
            await ctx.private_chat_manager.handle_dm_message(message, ctx)
            return
        # Channel messages — existing logic
        result = on_message_handler(message, ctx)
        if result == "command":
            await dispatch_command(message, ctx)
```

Note: the `message.author.bot` check moves into `on_message` directly since DMs bypass `on_message_handler`. The existing `on_message_handler` still has its own bot check for channel messages.

- [ ] **Step 5: Run existing tests to check nothing is broken**

Run: `uv run pytest -v`
Expected: All existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add discord_bot/bot.py
git commit -m "feat: wire up DM listener and PrivateChatManager in bot"
```

---

### Task 7: Inject Private Chat Notes Into `!process`

**Files:**
- Modify: `discord_bot/commands/dm.py`

- [ ] **Step 1: Add private chat note injection to handle_process**

In `discord_bot/commands/dm.py`, in the `handle_process` function, after the `_maybe_inject_private_prompt` call (line 147) and before `thinking_msg`, add:

```python
    # Notify Claude about any ongoing private conversations
    private_notes = ctx.private_chat_manager.build_process_notes()
    if private_notes:
        payload += "\n\n" + private_notes
```

The full block around lines 147-149 becomes:

```python
    payload = _maybe_inject_private_prompt(payload, ctx.player_map, exclude_character=character)

    # Notify Claude about any ongoing private conversations
    private_notes = ctx.private_chat_manager.build_process_notes()
    if private_notes:
        payload += "\n\n" + private_notes

    thinking_msg = await message.channel.send("*The DM is thinking...*")
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add discord_bot/commands/dm.py
git commit -m "feat: inject private chat notes into !process payloads"
```

---

### Task 8: End-to-End Smoke Test

**Files:**
- Modify: `tests/test_private_chat.py`

A more complete integration-style test that validates the full flow: start chat, exchange messages, `!done`, verify channel notifications and `[PUBLIC]` routing.

- [ ] **Step 1: Write integration test**

Append to `tests/test_private_chat.py`:

```python
def test_full_flow_start_chat_exchange_done():
    """Integration test: start → exchange → !done with [PUBLIC] output."""
    mgr = PrivateChatManager()

    # Mock context with different responses per call
    ctx = _make_ctx()
    responses = [
        "Interesting. What do you offer the guard?",              # First message
        "The guard considers your offer. He seems interested.",   # Second message
        "Good luck.\n[PUBLIC]The guard steps aside and opens the gate.[/PUBLIC]",  # !done
    ]
    ctx.claude_bridge.send = AsyncMock(side_effect=responses)

    msg1 = _make_message("I want to bribe the guard")
    msg2 = _make_message("I offer 50 gold")
    msg_done = _make_message("!done")

    loop = asyncio.get_event_loop()

    # Start chat
    loop.run_until_complete(mgr.handle_dm_message(msg1, ctx))
    assert mgr.is_active("12345")
    # Channel should have the "pulls aside" notification
    ctx.main_channel.send.assert_called_with("*Thorin pulls the DM aside for a private word...*")
    # Player should receive DM reply
    assert "What do you offer" in msg1.channel.send.call_args[0][0]

    # Continue chat
    loop.run_until_complete(mgr.handle_dm_message(msg2, ctx))
    assert mgr.get_active_chats()["12345"].message_count == 2

    # End chat
    ctx.main_channel.send.reset_mock()
    loop.run_until_complete(mgr.handle_dm_message(msg_done, ctx))
    assert not mgr.is_active("12345")

    # Verify channel received: return notification + [PUBLIC] content
    channel_calls = [c[0][0] for c in ctx.main_channel.send.call_args_list]
    assert channel_calls[0] == "*Thorin returns to the group.*"
    assert "guard steps aside" in channel_calls[1]

    # Verify player received the private wrap-up
    done_dm_text = msg_done.channel.send.call_args[0][0]
    assert "Good luck" in done_dm_text
```

- [ ] **Step 2: Run the integration test**

Run: `uv run pytest tests/test_private_chat.py::test_full_flow_start_chat_exchange_done -v`
Expected: PASS.

- [ ] **Step 3: Run the full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_private_chat.py
git commit -m "test: add end-to-end integration test for private DM conversations"
```

---

### Task 9: Register `!done` in Command Help

**Files:**
- Modify: `discord_bot/commands/help_cmd.py`

- [ ] **Step 1: Add private chat section to HELP_TEXT**

In `discord_bot/commands/help_cmd.py`, the `HELP_TEXT` string uses a `**Category:** / \`!command\`` format. Add a private messaging section. Replace the `HELP_TEXT` constant with:

```python
HELP_TEXT = """**D&D Discord Bot Commands:**

**Gameplay:**
`!dm <question>` -- Ask the DM a question (no plot advancement)
`!process <action>` -- Tell the DM what you do (advances the story)
`!private <question>` -- Ask the DM something privately (response via DM)
`!roll <dice>` -- Roll dice (e.g. `!roll 1d20+5`, `!roll 3d6`)

**Private Conversations:**
DM the bot directly to start a private conversation with the DM.
`!done` -- End the private conversation and publish observable results.

**Character:**
`!inventory` -- Show your character's equipment
`!status` -- Show your character summary (HP, level, gold)
`!join <character>` -- Link your Discord account to a character

**World:**
`!overview` -- Show current world state (locations, NPCs, quests)

**Session:**
`!session-start` -- Start a new DM session
`!session-end [summary]` -- End the current session

`!help` -- Show this message
"""
```

This adds the `!private` command (which was missing) and the new DM-based private conversation section.

- [ ] **Step 3: Run all tests**

Run: `uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add discord_bot/commands/help_cmd.py
git commit -m "docs: add private DM conversation info to help command"
```
