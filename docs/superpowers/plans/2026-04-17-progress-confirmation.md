# !progress Confirmation Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `!progress` command that gates plot advancement behind emoji confirmation from recently-active players, and `!pace` command to switch between active (2-min) and async (1-hour) confirmation timeout modes.

**Architecture:** Three layers — (1) `ActivityTracker` + `Pace` as pure Python state in `activity_tracker.py`, (2) `_advance_plot` helper extracted from `handle_process` in `dm.py` so both commands share the same plot-advancement logic, (3) `!progress`/`!pace` handlers in `progress.py` that compose these two pieces.

**Tech Stack:** Python 3.11+, discord.py, asyncio, pytest, pytest-asyncio

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `discord_bot/activity_tracker.py` | Create | `ActivityTracker` (last-seen dict) + `Pace` enum |
| `discord_bot/commands/dm.py` | Modify | Extract `_advance_plot` helper; slim down `handle_process` to call it |
| `discord_bot/commands/progress.py` | Create | `!pace` and `!progress` handlers |
| `discord_bot/bot.py` | Modify | Add `activity_tracker`, `pace`, `progress_pending` to `BotContext`; record activity in `on_message_handler` |
| `discord_bot/commands/__init__.py` | Modify | Import `progress` module |
| `tests/test_discord/test_activity_tracker.py` | Create | Unit tests for `ActivityTracker` and `Pace` |
| `tests/test_discord/test_progress_command.py` | Create | Tests for `!pace` and `!progress` |
| `tests/test_discord/test_bot_integration.py` | Modify | Add activity recording tests |
| `tests/test_discord/test_commands.py` | Modify | Add `pace` and `progress` to expected commands set |

---

## Task 1: ActivityTracker and Pace

**Files:**
- Create: `discord_bot/activity_tracker.py`
- Create: `tests/test_discord/test_activity_tracker.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_discord/test_activity_tracker.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from datetime import datetime, timedelta, timezone
from discord_bot.activity_tracker import ActivityTracker, Pace


class TestActivityTracker:
    def test_record_marks_user_active(self):
        tracker = ActivityTracker()
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=1)
        tracker.record("user1")
        assert "user1" in tracker.active_since(cutoff)

    def test_old_activity_not_returned(self):
        tracker = ActivityTracker()
        tracker._last_seen["user1"] = datetime.now(timezone.utc) - timedelta(minutes=20)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
        assert "user1" not in tracker.active_since(cutoff)

    def test_multiple_users_tracked_independently(self):
        tracker = ActivityTracker()
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=1)
        tracker.record("user1")
        tracker.record("user2")
        active = tracker.active_since(cutoff)
        assert "user1" in active
        assert "user2" in active

    def test_record_updates_stale_user(self):
        tracker = ActivityTracker()
        tracker._last_seen["user1"] = datetime.now(timezone.utc) - timedelta(minutes=20)
        tracker.record("user1")
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
        assert "user1" in tracker.active_since(cutoff)

    def test_empty_tracker_returns_empty_set(self):
        tracker = ActivityTracker()
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
        assert tracker.active_since(cutoff) == set()


class TestPace:
    def test_active_timeout_is_two_minutes(self):
        assert Pace.ACTIVE.value == 120

    def test_async_timeout_is_one_hour(self):
        assert Pace.ASYNC.value == 3600
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_discord/test_activity_tracker.py -v
```

Expected: `ModuleNotFoundError: No module named 'discord_bot.activity_tracker'`

- [ ] **Step 3: Create `discord_bot/activity_tracker.py`**

```python
from datetime import datetime, timezone
from enum import Enum


class ActivityTracker:
    def __init__(self):
        self._last_seen: dict[str, datetime] = {}

    def record(self, user_id: str) -> None:
        self._last_seen[user_id] = datetime.now(timezone.utc)

    def active_since(self, cutoff: datetime) -> set[str]:
        return {uid for uid, ts in self._last_seen.items() if ts >= cutoff}


class Pace(Enum):
    ACTIVE = 120
    ASYNC = 3600
```

- [ ] **Step 4: Run to verify passing**

```bash
uv run pytest tests/test_discord/test_activity_tracker.py -v
```

Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add discord_bot/activity_tracker.py tests/test_discord/test_activity_tracker.py
git commit -m "feat: add ActivityTracker and Pace for player activity tracking"
```

---

## Task 2: Update BotContext and on_message_handler

**Files:**
- Modify: `discord_bot/bot.py`
- Modify: `tests/test_discord/test_bot_integration.py`

- [ ] **Step 1: Write failing tests**

Add this class at the end of `tests/test_discord/test_bot_integration.py`:

```python
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
```

Also add `MagicMock` to the imports at the top of the file if not already there (it already is based on line 2: `from unittest.mock import AsyncMock, MagicMock`).

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_discord/test_bot_integration.py::TestActivityRecording -v
```

Expected: FAIL — `AttributeError` or `assert_called_once_with` fails because `record` is never called

- [ ] **Step 3: Update `discord_bot/bot.py`**

**3a.** Replace the import line `from dataclasses import dataclass` with:

```python
from dataclasses import dataclass, field
```

**3b.** Add after the existing discord_bot imports (after the `PrivateChatManager` import):

```python
from discord_bot.activity_tracker import ActivityTracker, Pace
```

**3c.** Replace the `BotContext` dataclass definition (lines 85–96) with:

```python
@dataclass
class BotContext:
    """Shared state passed to all command handlers."""
    config: dict
    message_buffer: MessageBuffer
    claude_bridge: ClaudeBridge
    player_map: PlayerMap
    channel_id: int
    campaign_dir: Path = None
    client: discord.Client = None
    main_channel: discord.TextChannel = None
    private_chat_manager: PrivateChatManager = None
    activity_tracker: ActivityTracker = field(default_factory=ActivityTracker)
    pace: Pace = Pace.ACTIVE
    progress_pending: bool = False
```

**3d.** In `on_message_handler`, replace these three lines:

```python
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id) or "unregistered"
    discord_name = ctx.player_map.get_discord_name(user_id) or message.author.display_name
```

With:

```python
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id)
    if character is not None:
        ctx.activity_tracker.record(user_id)
    character = character or "unregistered"
    discord_name = ctx.player_map.get_discord_name(user_id) or message.author.display_name
```

- [ ] **Step 4: Run all bot integration tests**

```bash
uv run pytest tests/test_discord/test_bot_integration.py -v
```

Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add discord_bot/bot.py tests/test_discord/test_bot_integration.py
git commit -m "feat: add activity_tracker, pace, progress_pending to BotContext; record activity on message"
```

---

## Task 3: Extract _advance_plot from handle_process

**Files:**
- Modify: `discord_bot/commands/dm.py`
- Modify: `tests/test_discord/test_dm_command.py`

- [ ] **Step 1: Write failing test for the extracted helper**

Add to `tests/test_discord/test_dm_command.py` (after the existing imports and before the first class):

```python
from discord_bot.commands.dm import _advance_plot
```

Add this class at the end of the file:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_discord/test_dm_command.py::TestAdvancePlot -v
```

Expected: `ImportError: cannot import name '_advance_plot'`

- [ ] **Step 3: Refactor `discord_bot/commands/dm.py`**

Replace the entire `handle_process` function (lines 121–171) with the following two functions. Keep all existing code above line 121 unchanged.

```python
async def _advance_plot(message, args: str, ctx) -> None:
    """Format buffer, send to Claude, route response. Called by !process and !progress."""
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id)
    discord_name = ctx.player_map.get_discord_name(user_id)

    delta = ctx.message_buffer.get_delta()
    ctx.message_buffer.mark_sent()
    log.info("Advancing plot: %d buffered messages, args=%r", len(delta), args[:50] if args else "")

    payload = ctx.message_buffer.format_for_claude(
        delta,
        active_player=discord_name,
        active_character=character,
        command_text=args,
        advance_plot=True,
    )
    payload = _maybe_inject_private_prompt(payload, ctx.player_map, exclude_character=character)

    private_notes = ctx.private_chat_manager.build_process_notes()
    if private_notes:
        payload += "\n\n" + private_notes

    thinking_msg = await message.channel.send("*The DM is thinking...*")
    try:
        response = await ctx.claude_bridge.send(payload)
        routed = route_response(response)

        if routed.public:
            for i in range(0, len(routed.public), DISCORD_MSG_LIMIT):
                await message.channel.send(routed.public[i:i + DISCORD_MSG_LIMIT])

        await _dispatch_whispers(routed.whispers, ctx.player_map, ctx.client, message.channel)
    except TimeoutError:
        log.warning("Claude timed out for plot advancement from %s", message.author.display_name)
        await message.channel.send("The DM took too long to respond. Try again or `!session-start` to restart.")
    except RuntimeError as e:
        log.error("Claude error for plot advancement from %s: %s", message.author.display_name, e)
        await message.channel.send(f"DM error: {e}")
    finally:
        await thinking_msg.delete()


@register("process")
async def handle_process(message, args: str, ctx) -> None:
    """Handle !process <text> -- advance the plot based on player actions."""
    dm_player = ctx.config.get("dm_player", "").strip()
    if dm_player and message.author.display_name != dm_player:
        log.info("!process blocked for %s (only %s may advance)", message.author.display_name, dm_player)
        await message.channel.send(f"Only **{dm_player}** can advance the story with `!process`.")
        return

    result = await _resolve_player(message, ctx)
    if result is None:
        return
    discord_name, character = result
    log.info("!process from %s (%s): args=%r", discord_name, character, args[:50] if args else "")
    await _advance_plot(message, args, ctx)
```

- [ ] **Step 4: Run all dm tests**

```bash
uv run pytest tests/test_discord/test_dm_command.py -v
```

Expected: all passed (existing routing tests still pass; new `TestAdvancePlot` passes)

- [ ] **Step 5: Commit**

```bash
git add discord_bot/commands/dm.py tests/test_discord/test_dm_command.py
git commit -m "refactor: extract _advance_plot helper from handle_process"
```

---

## Task 4: !pace command

**Files:**
- Create: `discord_bot/commands/progress.py`
- Create: `tests/test_discord/test_progress_command.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_discord/test_progress_command.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from discord_bot.activity_tracker import ActivityTracker, Pace


class FakeMessage:
    def __init__(self, user_id="111", display_name="DM"):
        self.author = MagicMock()
        self.author.id = user_id
        self.author.display_name = display_name
        self.channel = MagicMock()
        self.channel.send = AsyncMock()


class FakeCtx:
    def __init__(self, character="Thorin", discord_name="DM"):
        self.player_map = MagicMock()
        self.player_map.get_character.return_value = character
        self.player_map.get_discord_name.return_value = discord_name
        self.player_map.get_all.return_value = {
            "111": {"discord_name": discord_name, "character": character}
        }
        self.config = {}
        self.claude_bridge = AsyncMock()
        self.claude_bridge.is_active = True
        self.claude_bridge.send = AsyncMock(return_value="The plot thickens.")
        self.message_buffer = MagicMock()
        self.message_buffer.get_delta.return_value = []
        self.message_buffer.format_for_claude.return_value = "payload"
        self.activity_tracker = ActivityTracker()
        self.pace = Pace.ACTIVE
        self.progress_pending = False
        self.client = AsyncMock()
        self.private_chat_manager = MagicMock()
        self.private_chat_manager.build_process_notes.return_value = ""


@pytest.mark.asyncio
class TestPaceCommand:
    async def test_set_active(self):
        from discord_bot.commands.progress import handle_pace
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.pace = Pace.ASYNC

        await handle_pace(msg, "active", ctx)

        assert ctx.pace == Pace.ACTIVE
        text = msg.channel.send.call_args[0][0]
        assert "active" in text.lower()

    async def test_set_async(self):
        from discord_bot.commands.progress import handle_pace
        msg = FakeMessage()
        ctx = FakeCtx()

        await handle_pace(msg, "async", ctx)

        assert ctx.pace == Pace.ASYNC
        text = msg.channel.send.call_args[0][0]
        assert "async" in text.lower()

    async def test_no_args_shows_current_mode_and_timeout(self):
        from discord_bot.commands.progress import handle_pace
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.pace = Pace.ACTIVE

        await handle_pace(msg, "", ctx)

        text = msg.channel.send.call_args[0][0]
        assert "active" in text.lower()
        assert "2" in text

    async def test_unknown_arg_shows_current_mode(self):
        from discord_bot.commands.progress import handle_pace
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.pace = Pace.ASYNC

        await handle_pace(msg, "turbo", ctx)

        text = msg.channel.send.call_args[0][0]
        assert "async" in text.lower()
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_discord/test_progress_command.py::TestPaceCommand -v
```

Expected: `ModuleNotFoundError: No module named 'discord_bot.commands.progress'`

- [ ] **Step 3: Create `discord_bot/commands/progress.py`**

```python
"""!progress and !pace commands -- gated plot advancement with player confirmation."""

import logging
from discord_bot.commands import register
from discord_bot.activity_tracker import Pace

log = logging.getLogger("dm_bot.commands")


@register("pace")
async def handle_pace(message, args: str, ctx) -> None:
    """Handle !pace [active|async] -- set or display the confirmation timeout mode."""
    mode = args.strip().lower()
    if mode == "active":
        ctx.pace = Pace.ACTIVE
        await message.channel.send("Pace set to **active** (2-minute confirmation timeout).")
    elif mode == "async":
        ctx.pace = Pace.ASYNC
        await message.channel.send("Pace set to **async** (60-minute confirmation timeout).")
    else:
        timeout_min = ctx.pace.value // 60
        await message.channel.send(
            f"Current pace: **{ctx.pace.name.lower()}** ({timeout_min}-minute timeout). "
            f"Use `!pace active` or `!pace async`."
        )
```

- [ ] **Step 4: Run to verify passing**

```bash
uv run pytest tests/test_discord/test_progress_command.py::TestPaceCommand -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add discord_bot/commands/progress.py tests/test_discord/test_progress_command.py
git commit -m "feat: add !pace command to switch active/async confirmation timeout"
```

---

## Task 5: !progress command

**Files:**
- Modify: `discord_bot/commands/progress.py`
- Modify: `tests/test_discord/test_progress_command.py`

- [ ] **Step 1: Write failing tests**

Add the following helper and test class to the end of `tests/test_discord/test_progress_command.py`:

```python
def _make_reaction(emoji: str, msg_id: int, user_id: str):
    reaction = MagicMock()
    reaction.emoji = emoji
    reaction.message = MagicMock()
    reaction.message.id = msg_id
    user = MagicMock()
    user.id = user_id
    return reaction, user


@pytest.mark.asyncio
class TestProgressCommand:
    async def test_no_active_players_proceeds_without_confirmation(self):
        from discord_bot.commands.progress import handle_progress
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx()
        # Empty tracker — no other active players

        await handle_progress(msg, "we enter the cave", ctx)

        ctx.claude_bridge.send.assert_called_once()
        ctx.client.wait_for.assert_not_called()

    async def test_rejects_when_already_pending(self):
        from discord_bot.commands.progress import handle_progress
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.progress_pending = True

        await handle_progress(msg, "anything", ctx)

        ctx.claude_bridge.send.assert_not_called()
        text = msg.channel.send.call_args[0][0]
        assert "pending" in text.lower()

    async def test_rejects_unregistered_player(self):
        from discord_bot.commands.progress import handle_progress
        msg = FakeMessage()
        ctx = FakeCtx(character=None)

        await handle_progress(msg, "we attack", ctx)

        ctx.claude_bridge.send.assert_not_called()
        text = msg.channel.send.call_args[0][0]
        assert "!join" in text

    async def test_rejects_when_no_active_session(self):
        from discord_bot.commands.progress import handle_progress
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.claude_bridge.is_active = False

        await handle_progress(msg, "we attack", ctx)

        ctx.claude_bridge.send.assert_not_called()
        text = msg.channel.send.call_args[0][0]
        assert "session-start" in text

    async def test_dm_player_guard_blocks_non_dm(self):
        from discord_bot.commands.progress import handle_progress
        msg = FakeMessage(display_name="RandomPlayer")
        ctx = FakeCtx()
        ctx.config = {"dm_player": "GameMaster"}

        await handle_progress(msg, "advance", ctx)

        ctx.claude_bridge.send.assert_not_called()
        text = msg.channel.send.call_args[0][0]
        assert "GameMaster" in text

    async def test_all_active_players_confirm_advances_plot(self):
        from discord_bot.commands.progress import handle_progress
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx()
        ctx.player_map.get_all.return_value = {
            "111": {"discord_name": "DM", "character": "Thorin"},
            "222": {"discord_name": "Player2", "character": "Elara"},
        }
        ctx.activity_tracker.record("222")

        confirm_msg = AsyncMock()
        confirm_msg.id = 999
        msg.channel.send = AsyncMock(return_value=confirm_msg)

        reaction, user = _make_reaction("✅", 999, "222")
        ctx.client.wait_for = AsyncMock(return_value=(reaction, user))

        await handle_progress(msg, "we move north", ctx)

        ctx.claude_bridge.send.assert_called_once()
        assert ctx.progress_pending is False

    async def test_deny_aborts_and_posts_message(self):
        from discord_bot.commands.progress import handle_progress
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx()
        ctx.player_map.get_all.return_value = {
            "111": {"discord_name": "DM", "character": "Thorin"},
            "222": {"discord_name": "Player2", "character": "Elara"},
        }
        ctx.activity_tracker.record("222")

        confirm_msg = AsyncMock()
        confirm_msg.id = 999
        msg.channel.send = AsyncMock(return_value=confirm_msg)

        reaction, user = _make_reaction("❌", 999, "222")
        ctx.client.wait_for = AsyncMock(return_value=(reaction, user))

        await handle_progress(msg, "we move north", ctx)

        ctx.claude_bridge.send.assert_not_called()
        assert ctx.progress_pending is False
        texts = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("denied" in t.lower() or "aborted" in t.lower() for t in texts)

    async def test_timeout_proceeds_without_full_confirmation(self):
        from discord_bot.commands.progress import handle_progress
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx()
        ctx.player_map.get_all.return_value = {
            "111": {"discord_name": "DM", "character": "Thorin"},
            "222": {"discord_name": "Player2", "character": "Elara"},
        }
        ctx.activity_tracker.record("222")
        ctx.pace = Pace.ACTIVE

        confirm_msg = AsyncMock()
        confirm_msg.id = 999
        msg.channel.send = AsyncMock(return_value=confirm_msg)

        ctx.client.wait_for = AsyncMock(side_effect=asyncio.TimeoutError)

        await handle_progress(msg, "we move north", ctx)

        ctx.claude_bridge.send.assert_called_once()
        assert ctx.progress_pending is False

    async def test_pending_flag_cleared_after_deny(self):
        from discord_bot.commands.progress import handle_progress
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx()
        ctx.player_map.get_all.return_value = {
            "111": {"discord_name": "DM", "character": "Thorin"},
            "222": {"discord_name": "Player2", "character": "Elara"},
        }
        ctx.activity_tracker.record("222")

        confirm_msg = AsyncMock()
        confirm_msg.id = 999
        msg.channel.send = AsyncMock(return_value=confirm_msg)

        reaction, user = _make_reaction("❌", 999, "222")
        ctx.client.wait_for = AsyncMock(return_value=(reaction, user))

        await handle_progress(msg, "we move", ctx)

        assert ctx.progress_pending is False
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_discord/test_progress_command.py::TestProgressCommand -v
```

Expected: `ImportError: cannot import name 'handle_progress'`

- [ ] **Step 3: Add `!progress` to `discord_bot/commands/progress.py`**

Add these imports at the top of the file (after the existing imports):

```python
import asyncio
from datetime import datetime, timedelta, timezone
from discord_bot.commands.dm import _advance_plot
```

Add these constants after the `log = logging.getLogger(...)` line:

```python
_CONFIRM = "✅"
_DENY = "❌"
_ACTIVITY_WINDOW = timedelta(minutes=15)
```

Add this handler at the end of the file:

```python
@register("progress")
async def handle_progress(message, args: str, ctx) -> None:
    """Handle !progress <text> -- advance plot after active players confirm with emoji."""
    dm_player = ctx.config.get("dm_player", "").strip()
    if dm_player and message.author.display_name != dm_player:
        log.info("!progress blocked for %s", message.author.display_name)
        await message.channel.send(f"Only **{dm_player}** can advance the story with `!progress`.")
        return

    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id)
    if character is None:
        await message.channel.send("You're not registered. Use `!join <character_name>` first.")
        return
    if not ctx.claude_bridge.is_active:
        await message.channel.send("No active session. Use `!session-start` first.")
        return
    if ctx.progress_pending:
        await message.channel.send("A progress confirmation is already pending.")
        return

    cutoff = datetime.now(timezone.utc) - _ACTIVITY_WINDOW
    active_ids = ctx.activity_tracker.active_since(cutoff)
    registered = set(ctx.player_map.get_all().keys())
    candidates = (active_ids & registered) - {user_id}

    if not candidates:
        await _advance_plot(message, args, ctx)
        return

    mentions = " ".join(f"<@{uid}>" for uid in candidates)
    timeout_sec = ctx.pace.value
    timeout_min = timeout_sec // 60
    confirm_text = (
        f"**{message.author.display_name}** wants to advance the plot:\n"
        f"> {args or '(no description)'}\n\n"
        f"{mentions} — react {_CONFIRM} to confirm or {_DENY} to deny. "
        f"Timeout in {timeout_min} minute{'s' if timeout_min != 1 else ''}."
    )

    ctx.progress_pending = True
    confirm_msg = await message.channel.send(confirm_text)
    try:
        await confirm_msg.add_reaction(_CONFIRM)
        await confirm_msg.add_reaction(_DENY)
    except Exception:
        pass  # Missing reaction permissions; players can still react manually

    confirmed: set[str] = set()
    deadline = asyncio.get_event_loop().time() + timeout_sec

    def check(reaction, user):
        return (
            reaction.message.id == confirm_msg.id
            and str(user.id) in candidates
            and str(reaction.emoji) in (_CONFIRM, _DENY)
        )

    aborted = False
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            break
        try:
            reaction, user = await asyncio.wait_for(
                ctx.client.wait_for("reaction_add", check=check),
                timeout=remaining,
            )
            uid = str(user.id)
            if str(reaction.emoji) == _DENY:
                denier = ctx.player_map.get_discord_name(uid) or user.display_name
                await message.channel.send(
                    f"{_DENY} **{denier}** denied the progress. Plot advancement aborted."
                )
                aborted = True
                break
            confirmed.add(uid)
            if confirmed >= candidates:
                break
        except asyncio.TimeoutError:
            break

    ctx.progress_pending = False

    if not aborted:
        await _advance_plot(message, args, ctx)
```

- [ ] **Step 4: Run all progress tests**

```bash
uv run pytest tests/test_discord/test_progress_command.py -v
```

Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add discord_bot/commands/progress.py tests/test_discord/test_progress_command.py
git commit -m "feat: add !progress command with emoji confirmation gate"
```

---

## Task 6: Register module and update command registry test

**Files:**
- Modify: `discord_bot/commands/__init__.py`
- Modify: `tests/test_discord/test_commands.py`

- [ ] **Step 1: Update expected commands set and add parse tests**

In `tests/test_discord/test_commands.py`, replace the `test_all_commands_registered` test body:

```python
    def test_all_commands_registered(self):
        expected = {
            "dm", "process", "progress", "pace",
            "roll", "inventory", "status",
            "session-start", "session-end",
            "join", "help", "overview",
            "save", "restore", "list-saves",
            "private", "done", "internal-reload",
            "characters", "summary",
        }
        assert set(COMMANDS.keys()) == expected
```

Add these two tests to `TestParseCommand`:

```python
    def test_parse_progress_command(self):
        cmd, args = parse_command("!progress we enter the dungeon")
        assert cmd == "progress"
        assert args == "we enter the dungeon"

    def test_parse_pace_command(self):
        cmd, args = parse_command("!pace active")
        assert cmd == "pace"
        assert args == "active"
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_discord/test_commands.py::TestParseCommand::test_all_commands_registered -v
```

Expected: FAIL — `AssertionError` because `progress` and `pace` are not yet registered

- [ ] **Step 3: Update `discord_bot/commands/__init__.py`**

Replace line 33:

```python
from discord_bot.commands import dm, roll, inventory, status, session, join, help_cmd, overview, save, private, reload, characters  # noqa: E402, F401
```

With:

```python
from discord_bot.commands import dm, roll, inventory, status, session, join, help_cmd, overview, save, private, reload, characters, progress  # noqa: E402, F401
```

- [ ] **Step 4: Run the full test suite**

```bash
uv run pytest -v
```

Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add discord_bot/commands/__init__.py tests/test_discord/test_commands.py
git commit -m "feat: register !progress and !pace in command registry"
```
