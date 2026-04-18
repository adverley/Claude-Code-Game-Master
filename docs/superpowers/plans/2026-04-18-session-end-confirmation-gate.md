# Session-End Confirmation Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a majority-vote emoji confirmation gate to `!session-end` so any single player cannot unilaterally end the session.

**Architecture:** Mirror the `!progress` gate pattern exactly: look up recently-active registered players via `activity_tracker`, post a confirmation message with ✅/❌ reactions, collect until majority confirms or anyone denies, with a fixed 5-minute timeout. Extract the existing end logic into a `_end_session` helper so the gate can call it on success.

**Tech Stack:** Python, discord.py, asyncio, `activity_tracker.ActivityTracker` (already on `BotContext`)

---

## File Map

| File | Change |
|------|--------|
| `discord_bot/bot.py` | Add `session_end_pending: bool = False` to `BotContext` dataclass |
| `discord_bot/commands/session.py` | Extract `_end_session` helper; replace `handle_session_end` body with gate logic |
| `tests/test_discord/test_session_commands.py` | Update existing tests for refactored helper; add gate tests |

---

### Task 1: Add `session_end_pending` to `BotContext`

**Files:**
- Modify: `discord_bot/bot.py:98-100`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_discord/test_session_commands.py` inside `TestSessionEnd`:

```python
async def test_session_end_pending_flag_exists_on_ctx(self):
    from discord_bot.bot import BotContext
    from discord_bot.activity_tracker import ActivityTracker, Pace
    from dataclasses import fields
    field_names = {f.name for f in fields(BotContext)}
    assert "session_end_pending" in field_names
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_discord/test_session_commands.py::TestSessionEnd::test_session_end_pending_flag_exists_on_ctx -v
```

Expected: FAIL with `AssertionError`

- [ ] **Step 3: Add field to `BotContext`**

In `discord_bot/bot.py`, after line 100 (`progress_pending: bool = False`), add:

```python
    session_end_pending: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_discord/test_session_commands.py::TestSessionEnd::test_session_end_pending_flag_exists_on_ctx -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add discord_bot/bot.py tests/test_discord/test_session_commands.py
git commit -m "feat: add session_end_pending flag to BotContext"
```

---

### Task 2: Extract `_end_session` helper and update existing tests

**Files:**
- Modify: `discord_bot/commands/session.py`
- Modify: `tests/test_discord/test_session_commands.py`

- [ ] **Step 1: Update `FakeCtx` in `test_session_commands.py` to include gate fields**

Replace the existing `FakeCtx` class with:

```python
class FakeCtx:
    def __init__(self, active=False):
        from discord_bot.activity_tracker import ActivityTracker, Pace
        self.claude_bridge = MagicMock()
        self.claude_bridge.is_active = active
        self.claude_bridge.start_session = MagicMock(return_value="discord-test-123")
        self.claude_bridge.send_init = AsyncMock(return_value="Welcome adventurers! You stand at the entrance of a dark cave.")
        self.claude_bridge.send = AsyncMock(return_value="Session ended. The party rests for the night.")
        self.claude_bridge.end_session = MagicMock()
        self.claude_bridge._project_dir = "/fake/path"
        self.player_map = MagicMock()
        self.player_map.get_all.return_value = {
            "111": {"discord_name": "Erik", "character": "thorin"}
        }
        self.config = {}
        self.campaign_dir = Path("world-state/campaigns/test-campaign")
        mock_dm_user = AsyncMock()
        mock_dm_user.send = AsyncMock()
        self.client = AsyncMock()
        self.client.fetch_user = AsyncMock(return_value=mock_dm_user)
        self.activity_tracker = ActivityTracker()
        self.session_end_pending = False
```

Also update `FakeMessage` to include `author.id`:

```python
class FakeMessage:
    def __init__(self, user_id="111"):
        self.author = MagicMock()
        self.author.id = user_id
        self.author.display_name = "Erik"
        self.channel = MagicMock()
        self.channel.send = AsyncMock()
```

- [ ] **Step 2: Run existing tests to confirm they still pass before refactor**

```bash
uv run pytest tests/test_discord/test_session_commands.py -v
```

Expected: all existing tests PASS (baseline)

- [ ] **Step 3: Extract `_end_session` helper in `session.py`**

Replace the contents of `discord_bot/commands/session.py` with:

```python
"""!session-start and !session-end commands."""

import asyncio
import logging
import shlex
from datetime import timedelta

from discord_bot.commands import register
from discord_bot.commands.dm import _dispatch_whispers
from discord_bot.response_router import route_response

log = logging.getLogger("dm_bot.commands")

DISCORD_MSG_LIMIT = 2000
_CONFIRM = "✅"
_DENY = "❌"
_ACTIVITY_WINDOW = timedelta(minutes=15)
_SESSION_END_TIMEOUT = 300  # 5 minutes, fixed


@register("session-start")
async def handle_session_start(message, args: str, ctx) -> None:
    """Start a new Claude DM session."""
    discord_name = message.author.display_name
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id) or "unregistered"

    if ctx.claude_bridge.is_active:
        log.info("!session-start from %s (%s): rejected, session already active", discord_name, character)
        await message.channel.send("A session is already active. Use `!session-end` first.")
        return

    campaign = ctx.campaign_dir.name
    log.info("!session-start from %s (%s): starting campaign %r", discord_name, character, campaign)
    await message.channel.send(f"*Starting DM session for **{campaign}**...*")

    ctx.claude_bridge.start_session(campaign)
    players = ctx.player_map.get_all()

    try:
        response = await ctx.claude_bridge.send_init(campaign, players)
        routed = route_response(response)

        if routed.public:
            for i in range(0, len(routed.public), DISCORD_MSG_LIMIT):
                await message.channel.send(routed.public[i:i + DISCORD_MSG_LIMIT])

        await _dispatch_whispers(routed.whispers, ctx.player_map, ctx.client, message.channel)
        log.info("!session-start from %s (%s): session started successfully", discord_name, character)
    except (TimeoutError, RuntimeError) as e:
        log.error("!session-start from %s (%s): failed: %s", discord_name, character, e)
        ctx.claude_bridge.end_session()
        await message.channel.send(f"Failed to start session: {e}")


async def _end_session(message, summary: str, ctx) -> None:
    """Run the session-end narrative and save. Called after gate passes."""
    await message.channel.send("*Ending session...*")
    try:
        prompt = (
            f"The session is ending. Please wrap up the narrative with a closing scene. Summary: {summary}\n\n"
            f"Keep all DM-internal information (pending consequences, upcoming events, future plot) "
            f"inside [MENTAL MODEL]...[/MENTAL MODEL] tags — it will be filtered before reaching players."
        )
        response = await ctx.claude_bridge.send(prompt)
        routed = route_response(response)
        if routed.public:
            for i in range(0, len(routed.public), DISCORD_MSG_LIMIT):
                await message.channel.send(routed.public[i:i + DISCORD_MSG_LIMIT])
        await _dispatch_whispers(routed.whispers, ctx.player_map, ctx.client, message.channel)
    except (TimeoutError, RuntimeError) as e:
        log.error("_end_session error: %s", e)
        await message.channel.send(f"Error during session end: {e}")
    finally:
        try:
            project_dir = str(ctx.claude_bridge._project_dir)
            safe_summary = shlex.quote(summary)
            proc = await asyncio.create_subprocess_shell(
                f"bash tools/dm-session.sh end {safe_summary}",
                cwd=project_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=30.0)
        except Exception:
            pass
        ctx.claude_bridge.end_session()
        await message.channel.send("*Session ended.*")


@register("session-end")
async def handle_session_end(message, args: str, ctx) -> None:
    """End the current DM session, with majority-vote confirmation gate."""
    discord_name = message.author.display_name
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id) or "unregistered"

    if not ctx.claude_bridge.is_active:
        log.info("!session-end from %s (%s): rejected, no active session", discord_name, character)
        await message.channel.send("No active session. Use `!session-start` first.")
        return

    if ctx.session_end_pending:
        log.info("!session-end from %s (%s): rejected, already pending", discord_name, character)
        await message.channel.send("A session-end confirmation is already pending.")
        return

    summary = args.strip() if args.strip() else "Session ended by player request."
    log.info("!session-end from %s (%s): requested, summary=%r", discord_name, character, summary[:80])

    from datetime import datetime, timezone
    cutoff = datetime.now(timezone.utc) - _ACTIVITY_WINDOW
    active_ids = ctx.activity_tracker.active_since(cutoff)
    registered = set(ctx.player_map.get_all().keys())
    candidates = (active_ids & registered) - {user_id}

    if not candidates:
        await _end_session(message, summary, ctx)
        return

    mentions = " ".join(f"<@{uid}>" for uid in candidates)
    confirm_text = (
        f"**{discord_name}** wants to end the session.\n"
        f'Summary: "{summary}"\n\n'
        f"{mentions} — react {_CONFIRM} to confirm or {_DENY} to deny. "
        f"Timeout in 5 minutes."
    )

    ctx.session_end_pending = True
    try:
        confirm_msg = await message.channel.send(confirm_text)
        try:
            await confirm_msg.add_reaction(_CONFIRM)
            await confirm_msg.add_reaction(_DENY)
        except Exception:
            pass

        confirmed: set[str] = set()
        deadline = asyncio.get_running_loop().time() + _SESSION_END_TIMEOUT

        def check(reaction, user):
            return (
                reaction.message.id == confirm_msg.id
                and str(user.id) in candidates
                and str(reaction.emoji) in (_CONFIRM, _DENY)
            )

        aborted = False
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
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
                    log.info("!session-end denied by %s", denier)
                    await message.channel.send(
                        f"{_DENY} **{denier}** denied the session end. Aborted."
                    )
                    aborted = True
                    break
                confirmed.add(uid)
                if len(confirmed) > len(candidates) / 2:
                    break
            except asyncio.TimeoutError:
                break

        if aborted:
            return
        if len(confirmed) <= len(candidates) / 2:
            await message.channel.send(
                f"Session-end timed out without majority confirmation. Aborted."
            )
            return
    finally:
        ctx.session_end_pending = False

    await _end_session(message, summary, ctx)
```

- [ ] **Step 4: Run existing tests to confirm they still pass**

```bash
uv run pytest tests/test_discord/test_session_commands.py -v
```

Expected: all existing tests PASS

- [ ] **Step 5: Commit**

```bash
git add discord_bot/commands/session.py tests/test_discord/test_session_commands.py
git commit -m "refactor: extract _end_session helper and add gate scaffold to session-end"
```

---

### Task 3: Add gate tests

**Files:**
- Modify: `tests/test_discord/test_session_commands.py`

Helper function to add near the top of the file (after imports):

```python
def _make_reaction(emoji: str, msg_id: int, user_id: str):
    reaction = MagicMock()
    reaction.emoji = emoji
    reaction.message = MagicMock()
    reaction.message.id = msg_id
    user = MagicMock()
    user.id = user_id
    return reaction, user
```

- [ ] **Step 1: Write all gate tests**

Add a new test class to `tests/test_discord/test_session_commands.py`:

```python
@pytest.mark.asyncio
class TestSessionEndGate:
    async def test_no_other_active_players_ends_immediately(self):
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx(active=True)
        # No other players recorded in activity tracker

        await handle_session_end(msg, "we won", ctx)

        ctx.claude_bridge.send.assert_called_once()
        ctx.claude_bridge.end_session.assert_called_once()

    async def test_rejects_when_already_pending(self):
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx(active=True)
        ctx.session_end_pending = True

        await handle_session_end(msg, "we won", ctx)

        ctx.claude_bridge.send.assert_not_called()
        text = msg.channel.send.call_args[0][0]
        assert "pending" in text.lower()

    async def test_majority_confirm_ends_session(self):
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx(active=True)
        ctx.player_map.get_all.return_value = {
            "111": {"discord_name": "Erik", "character": "thorin"},
            "222": {"discord_name": "Kira", "character": "elara"},
            "333": {"discord_name": "Brom", "character": "brom"},
        }
        ctx.activity_tracker.record("222")
        ctx.activity_tracker.record("333")

        confirm_msg = AsyncMock()
        confirm_msg.id = 999
        msg.channel.send = AsyncMock(return_value=confirm_msg)

        # "222" confirms — that's 1 out of 2 candidates = exactly 50%, not majority
        # "333" also confirms — that's 2 out of 2 = majority
        reactions = [
            _make_reaction("✅", 999, "222"),
            _make_reaction("✅", 999, "333"),
        ]
        ctx.client.wait_for = AsyncMock(side_effect=reactions)

        await handle_session_end(msg, "we won", ctx)

        ctx.claude_bridge.send.assert_called_once()
        ctx.claude_bridge.end_session.assert_called_once()
        assert ctx.session_end_pending is False

    async def test_single_deny_aborts(self):
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx(active=True)
        ctx.player_map.get_all.return_value = {
            "111": {"discord_name": "Erik", "character": "thorin"},
            "222": {"discord_name": "Kira", "character": "elara"},
        }
        ctx.player_map.get_discord_name.return_value = "Kira"
        ctx.activity_tracker.record("222")

        confirm_msg = AsyncMock()
        confirm_msg.id = 999
        msg.channel.send = AsyncMock(return_value=confirm_msg)

        reaction, user = _make_reaction("❌", 999, "222")
        ctx.client.wait_for = AsyncMock(return_value=(reaction, user))

        await handle_session_end(msg, "we won", ctx)

        ctx.claude_bridge.send.assert_not_called()
        ctx.claude_bridge.end_session.assert_not_called()
        assert ctx.session_end_pending is False
        texts = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("denied" in t.lower() or "aborted" in t.lower() for t in texts)

    async def test_timeout_without_majority_aborts(self):
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx(active=True)
        ctx.player_map.get_all.return_value = {
            "111": {"discord_name": "Erik", "character": "thorin"},
            "222": {"discord_name": "Kira", "character": "elara"},
            "333": {"discord_name": "Brom", "character": "brom"},
        }
        ctx.activity_tracker.record("222")
        ctx.activity_tracker.record("333")

        confirm_msg = AsyncMock()
        confirm_msg.id = 999
        msg.channel.send = AsyncMock(return_value=confirm_msg)

        # Only 1 of 2 confirms, then timeout — not a majority
        reactions = [
            _make_reaction("✅", 999, "222"),
            asyncio.TimeoutError,
        ]

        call_count = 0
        async def side_effect(*a, **kw):
            nonlocal call_count
            val = reactions[min(call_count, len(reactions) - 1)]
            call_count += 1
            if val is asyncio.TimeoutError:
                raise asyncio.TimeoutError
            return val

        ctx.client.wait_for = side_effect

        await handle_session_end(msg, "we won", ctx)

        ctx.claude_bridge.send.assert_not_called()
        assert ctx.session_end_pending is False
        texts = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("timed out" in t.lower() or "aborted" in t.lower() for t in texts)

    async def test_pending_flag_cleared_after_deny(self):
        msg = FakeMessage(user_id="111")
        ctx = FakeCtx(active=True)
        ctx.player_map.get_all.return_value = {
            "111": {"discord_name": "Erik", "character": "thorin"},
            "222": {"discord_name": "Kira", "character": "elara"},
        }
        ctx.player_map.get_discord_name.return_value = "Kira"
        ctx.activity_tracker.record("222")

        confirm_msg = AsyncMock()
        confirm_msg.id = 999
        msg.channel.send = AsyncMock(return_value=confirm_msg)

        reaction, user = _make_reaction("❌", 999, "222")
        ctx.client.wait_for = AsyncMock(return_value=(reaction, user))

        await handle_session_end(msg, "we won", ctx)

        assert ctx.session_end_pending is False
```

- [ ] **Step 2: Run all new tests to verify they pass**

```bash
uv run pytest tests/test_discord/test_session_commands.py::TestSessionEndGate -v
```

Expected: all 6 tests PASS

- [ ] **Step 3: Run full test suite to check for regressions**

```bash
uv run pytest -v
```

Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_discord/test_session_commands.py
git commit -m "test: add session-end confirmation gate tests"
```
