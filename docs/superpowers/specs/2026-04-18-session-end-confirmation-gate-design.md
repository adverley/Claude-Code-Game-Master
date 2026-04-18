# Session-End Confirmation Gate — Design Spec

**Date:** 2026-04-18  
**Status:** Approved

## Problem

`!session-end` has no permission checks — any player can end the session mid-play, with an arbitrary summary. This enables trolling: disrupting the narrative or nuking session state without group consent.

`!session-start` is intentionally open (anyone can start), so no change needed there.

## Solution

Add a majority-vote confirmation gate to `!session-end`, modelled on the existing `!progress` gate.

## Flow

1. Player calls `!session-end [summary]`
2. Reject if no active session
3. Reject if `session_end_pending` is already True
4. Look up recently-active registered players via `activity_tracker.active_since(cutoff)` (15-min window), excluding the requester
5. If no other active players → end immediately (no gate needed)
6. Otherwise → post confirmation message mentioning all candidates with ✅/❌ reactions, 5-minute fixed timeout
7. Collect reactions:
   - Any ❌ → abort immediately, post denial message
   - `len(confirmed) > len(candidates) / 2` → proceed
   - Timeout without majority → abort, post timeout message
8. On proceed → run existing end logic (narrative prompt + `dm-session.sh end`)

## Implementation Details

### `discord_bot/bot.py`
- Add `session_end_pending: bool = False` to `BotContext` dataclass

### `discord_bot/commands/session.py`
- Extract existing end logic (narrative + subprocess save) into `_end_session(message, summary, ctx)` helper
- Replace `handle_session_end` body with gate logic that calls `_end_session` on success
- Timeout: `300` seconds (hardcoded, not `!pace`)
- Activity window: `timedelta(minutes=15)` (same as `!progress`)
- Majority threshold: `len(confirmed) > len(candidates) / 2`
- `session_end_pending` flag set/cleared in `try/finally` (same pattern as `progress_pending`)

### No new config keys
Reuses `ctx.activity_tracker` already present on `BotContext`.

## Confirmation Message Format

```
**{requester}** wants to end the session.
Summary: "{summary}"

{mentions} — react ✅ to confirm or ❌ to deny.
Timeout in 5 minutes.
```

## Tests

- Gate skipped when no other active players (fast-path)
- Majority confirm → `_end_session` called
- Single ❌ → abort, `_end_session` not called
- Timeout without majority → abort, `_end_session` not called
- `session_end_pending` cleared in all exit paths
