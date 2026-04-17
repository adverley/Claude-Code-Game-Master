# !progress confirmation gate — design spec

**Date:** 2026-04-17

## Overview

Add a `!progress` command that gates plot advancement behind emoji confirmation from recently-active players. A companion `!pace` command switches between active (2-min timeout) and async (1-hour timeout) play modes.

---

## New files

| File | Purpose |
|------|---------|
| `discord_bot/activity_tracker.py` | `ActivityTracker` class + `Pace` enum |
| `discord_bot/commands/progress.py` | `!progress` and `!pace` handlers |

## Modified files

| File | Change |
|------|--------|
| `discord_bot/bot.py` | Add `activity_tracker`, `pace`, `progress_pending` to `BotContext`; record activity in `on_message_handler` |
| `discord_bot/commands/__init__.py` | Import `progress` module |

---

## ActivityTracker (`discord_bot/activity_tracker.py`)

```python
class ActivityTracker:
    def record(self, user_id: str) -> None: ...
    def active_since(self, cutoff: datetime) -> set[str]: ...
```

- Stores `datetime.now(UTC)` per user ID on every call to `record()`
- `active_since(cutoff)` returns user IDs whose last-seen timestamp >= cutoff
- In-memory only — resets on bot restart (acceptable: restart within a 15-min window is rare)

## Pace (`discord_bot/activity_tracker.py`)

```python
class Pace(Enum):
    ACTIVE = 120    # 2 minutes
    ASYNC  = 3600   # 1 hour
```

- Stored as `ctx.pace`, defaults to `Pace.ACTIVE`
- Resets to `ACTIVE` on bot restart; DM sets it once at session start if needed

---

## BotContext additions (`discord_bot/bot.py`)

```python
activity_tracker: ActivityTracker = field(default_factory=ActivityTracker)
pace: Pace = Pace.ACTIVE
progress_pending: bool = False
```

`on_message_handler` calls `ctx.activity_tracker.record(user_id)` for every non-bot, registered-player message (including commands — they signal presence even if not buffered).

---

## `!progress` command flow

**Guard checks (in order):**
1. `dm_player` check — same as `!process`; only the configured DM may run it
2. Active session check
3. `progress_pending` check — reject with "A progress confirmation is already pending." if true

**Active player detection:**
- Cutoff = `now - 15 minutes`
- Candidates = `activity_tracker.active_since(cutoff)` ∩ `set(player_map.get_all().keys())` − `{initiator_user_id}`
- If candidates is empty → skip confirmation, proceed directly to plot advancement

**Confirmation gate:**
- Set `ctx.progress_pending = True`
- Post a public message: lists the progress text, tags each active player, instructs ✅ to confirm / ❌ to deny
- Bot adds ✅ and ❌ reactions to the message to guide players
- Collect reactions with `client.wait_for("reaction_add", check=..., timeout=remaining)` in a loop:
  - Only count reactions from players in the candidate set on the confirmation message
  - ❌ from any candidate → edit message to show who denied, abort, set `progress_pending = False`, return
  - ✅ from a candidate → add to confirmed set; when confirmed == candidates, proceed
  - `asyncio.TimeoutError` → break loop (silent non-responders lose their vote), proceed

**On proceed:**
- Set `progress_pending = False`
- Run identical logic to `!process`: `message_buffer.get_delta()` → `mark_sent()` → format payload → send to Claude → route response

---

## `!pace` command

| Invocation | Effect |
|------------|--------|
| `!pace active` | Sets `ctx.pace = Pace.ACTIVE` (2-min timeout), confirms in channel |
| `!pace async` | Sets `ctx.pace = Pace.ASYNC` (1-hour timeout), confirms in channel |
| `!pace` | Shows current mode and timeout duration |

No persistence — resets to `active` on restart.

---

## Error handling

| Scenario | Behaviour |
|----------|-----------|
| No active session | "No active session. Use `!session-start` first." |
| Not a registered player | "You're not registered. Use `!join <character_name>` first." |
| `!progress` while one pending | "A progress confirmation is already pending." |
| Claude timeout after confirmation | Same handling as `!process` — show timeout message |
| Bot loses permission to add reactions | Fall through: post confirmation message without bot reactions; players can still react manually |

---

## Out of scope

- Persisting pace across restarts
- Cancelling a pending confirmation via command
- Tracking activity across bot restarts
