# Discord Private Messages Design Spec

## Overview

Extend the Discord bot with private messaging support: players can request private DM responses via `!private <message>`, and the DM (Claude) can proactively whisper to individual players using `[PRIVATE:character_name]` markers in its responses. The channel always sees a brief acknowledgement when a private exchange occurs, so other players know something happened without seeing the content.

## Goals

- Let players ask the DM something privately (`!private <message>`)
- Let Claude send secrets to specific players mid-narrative (e.g. only one player notices a trap)
- Keep other players aware a private exchange happened, not what was said
- Reuse existing player-map infrastructure — no new registration flow needed

## Architecture

```
!private <msg>                        !dm <msg>
     │                                    │
     ▼                                    ▼
private.py handler                   dm.py handler
     │                                    │
     │  full response → DM player         │  response → ResponseRouter
     │  channel: "🤫 DM whispers..."      │       │
     └────────────────────────────────────┘       ▼
                                         public → channel
                                         whispers → DM each player
                                         channel: "🤫 DM whispers to X..." per whisper
```

## Components

### 1. ResponseRouter (`discord_bot/response_router.py`)

Pure parsing utility — no I/O, fully unit-testable.

**Input:** raw Claude response string

**Output:**
```python
@dataclass
class RoutedResponse:
    public: str                        # text for the channel (may be empty)
    whispers: list[tuple[str, str]]    # [(character_name, text), ...]
```

**Marker format:**
```
[PRIVATE:thorin]Only you notice a trapdoor beneath the merchant's desk.[/PRIVATE]
```

- Strips `[PRIVATE:name]...[/PRIVATE]` blocks from `public`
- Collects them in `whispers` as `(character_name, text)` tuples
- Character name matching is case-insensitive
- Multiple `[PRIVATE:...]` blocks in one response are all handled
- If no markers found, returns full text as `public` with empty `whispers`

### 2. `!private` command (`discord_bot/commands/private.py`)

Behaves identically to `!dm` with two differences:

1. The entire Claude response is DMed to the requesting player — `ResponseRouter` is not needed since the whole response is private by definition
2. Channel receives: *"🤫 The DM whispers to Thorin..."* immediately after the DM is sent

Prompt sent to Claude appends: *"This is a private message to this player only — do not address the full party."*

### 3. `!dm` handler update (`discord_bot/commands/dm.py`)

After receiving Claude's response, pass it through `ResponseRouter` before posting:

1. Post `public` text to channel (skip if empty)
2. For each `(character, text)` in `whispers`:
   - Look up Discord user ID via `PlayerMap.get_user_id_by_character(character)`
   - Fetch user and send DM
   - Post *"🤫 The DM whispers to {character}..."* to channel

### 4. PlayerMap update (`discord_bot/player_map.py`)

Add one method:

```python
def get_user_id_by_character(self, character_name: str) -> Optional[str]:
    """Reverse lookup: character name → Discord user ID. Case-insensitive."""
    name = character_name.lower()
    for user_id, data in self._data["players"].items():
        if data["character"].lower() == name:
            return user_id
    return None
```

No changes to `player-map.json` structure — Discord user IDs are already stored as keys via `!join`.

### 5. BotContext update (`discord_bot/bot.py`)

Add `client: discord.Client` field to `BotContext` so command handlers can call `await client.fetch_user(user_id)`.

## Session Initialization

`!session-start` prompt gets one added line in the DM role instructions:

> "To send a private message to a specific player, wrap it in `[PRIVATE:character_name]...[/PRIVATE]`. Everything outside these markers is posted publicly to the channel."

## Error Handling

| Scenario | Handling |
|----------|----------|
| Character not in player map | Log warning, skip DM, no channel ack for that whisper |
| Player has DMs disabled | Catch `discord.Forbidden`, post in channel: *"Thorin, your DMs are closed — enable them to receive private messages"* |
| Empty public + failed DM | Post generic error to channel so the exchange isn't silently lost |
| `!private` by unregistered player | Bot replies: *"Use `!join <character_name>` first"* |

## Scope Boundaries (Not Building)

- No group DMs (multiple recipients for one message)
- No persistent private message history
- No player-to-player private messaging via bot
- No opt-out for the channel acknowledgement
