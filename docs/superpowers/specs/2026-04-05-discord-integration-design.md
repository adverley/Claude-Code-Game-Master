# Discord Integration Design Spec

## Overview

A lightweight Discord bot running on the user's local machine that exposes the existing D&D Dungeon Master system to a group chat. Players interact via Discord commands, the bot pipes them into a persistent Claude Code CLI session, and Claude responds as DM with full access to the existing tools, skills, and campaign state.

## Goals

- Let a group of friends play D&D together via Discord with Claude as DM
- Track all messages in the channel for narrative context
- Respond to specific trigger commands
- Each player has their own character
- Use the existing campaign JSON state system — no migration
- Minimize token usage via persistent sessions and mechanical command shortcuts

## Architecture

```
Discord Channel
    │
    ▼
Discord Bot (local, discord.py)
    │
    ├── Tracks ALL messages in rolling buffer (50 messages)
    │
    ├── Mechanical commands (!roll, !inventory, !status)
    │       └── Call lib/ Python managers directly (zero tokens)
    │
    └── Narrative commands (!dm)
            └── Pipe message delta to persistent Claude Code session
                    │
                    ├── claude --session-id <id> --print "<context>"
                    ├── Full access to tools/, lib/, skills, agents
                    └── Response posted back to Discord
```

Single campaign, single channel, single persistent session per play session.

## Bot Core

A Python Discord bot using `discord.py`, running locally as a single process.

**Responsibilities:**
- Connect to Discord, listen to one configured channel
- Track all messages in a rolling in-memory buffer (last 50 messages)
- On trigger commands, format new messages since last Claude invocation and pipe to `claude --session-id <id> --print`
- Post Claude's response back to the channel
- Map Discord users to player characters via `player-map.json`

## Commands

| Command | Type | Behavior |
|---------|------|----------|
| `!dm <text>` | Narrative | Sends message buffer delta + command to Claude |
| `!roll <check>` | Mechanical | Calls `lib/dice.py` directly, posts result |
| `!inventory` | Mechanical | Calls `lib/player_manager.py` directly for requesting player |
| `!status` | Mechanical | Calls `lib/player_manager.py` directly for requesting player |
| `!session-start` | Lifecycle | Starts a new Claude Code persistent session, loads campaign |
| `!session-end [summary]` | Lifecycle | Ends session via `tools/dm-session.sh end`, discards session ID |
| `!join <character_name>` | Setup | Links Discord user to a character file |
| `!help` | Info | Lists available commands |

Mechanical commands skip Claude entirely for speed and zero token cost.

## Message Tracking & Context Passing

**Message buffer:** In-memory rolling list of last 50 messages. Each entry stores:
- Discord username
- Character name (from player map)
- Timestamp
- Message content
- Whether it was a command or regular chat

**On `!dm` trigger:** The bot collects all messages since the last Claude invocation and formats them as:

```
[Discord context since last DM response]
[14:32] Erik (playing Thorin): I don't trust this merchant
[14:33] Sara (playing Elara): agreed, let's check the back room
[14:35] Erik (playing Thorin): !dm I quietly move to the back door and listen

Active player: Erik (Thorin)
Command: I quietly move to the back door and listen
```

Only the **delta** (new messages since last response) is sent. The persistent session retains everything before that.

## Session Lifecycle

### Starting a session (`!session-start`)

1. Generate session ID: `discord-<campaign>-<timestamp>`
2. Call `claude --session-id <id> --print` with initialization prompt:
   - Load DM rules from `.claude/rules/dm-rules.md`
   - Run `bash tools/dm-session.sh start` and `bash tools/dm-session.sh context`
   - Provide player-character mappings
   - Set DM role: "You are the DM for a Discord multi-player session. Respond to commands from the channel. Narrate scenes, resolve actions, track state."
3. Post Claude's opening narration to the channel

### During play

Each `!dm` command sends the message delta to the same session. Claude responds in character. Bot posts the response.

### Ending a session (`!session-end [summary]`)

1. Send final message to Claude: "Session ending. Summarize and save."
2. Claude runs `bash tools/dm-session.sh end "<summary>"`
3. Bot posts session summary to Discord
4. Session ID discarded

### Crash recovery

If the bot restarts mid-session, the Claude Code session is lost. Campaign state is safe in JSON. Run `!session-start` to resume from saved state.

## Multi-Player Character System

### New directory structure

```
world-state/campaigns/<name>/
├── characters/
│   ├── thorin.json
│   ├── elara.json
│   └── gandalf.json
├── player-map.json
├── npcs.json              (unchanged)
├── locations.json         (unchanged)
├── campaign-overview.json (unchanged)
├── session-log.md         (unchanged)
└── ...
```

### player-map.json

```json
{
  "players": {
    "123456789": { "discord_name": "Erik", "character": "thorin" },
    "987654321": { "discord_name": "Sara", "character": "elara" }
  }
}
```

### Player resolution

- Bot looks up Discord user ID in `player-map.json` to determine which character is acting
- Passes character name to Claude or `lib/` managers
- Claude can update any character during narration (e.g. area-of-effect damage)

### Player registration

`!join <character_name>` links a Discord user to their character. Run once during campaign setup.

### Impact on existing code

`player_manager.py` needs a small modification to accept a character path parameter instead of always reading `character.json`. This is the only change to existing code.

## Configuration & Setup

### Bot config (`discord-bot/config.json`, gitignored)

```json
{
  "bot_token": "YOUR_BOT_TOKEN",
  "channel_id": "123456789",
  "campaign": "lost-mines",
  "message_buffer_size": 50,
  "session_id": null
}
```

### Discord bot setup steps

1. Go to Discord Developer Portal, create application
2. Create bot, copy token
3. Enable **Message Content Intent** (required to read messages)
4. Generate invite URL with permissions: Read Messages, Send Messages, Read Message History
5. Invite bot to server
6. Put token and channel ID in `config.json`

### Project structure

```
discord-bot/
├── bot.py              # Main bot — discord.py event loop
├── config.json         # Bot token, channel, campaign (gitignored)
├── config.example.json # Template
├── message_buffer.py   # Rolling message tracker
├── claude_bridge.py    # Spawns claude CLI, manages session
├── commands/
│   ├── dm.py           # !dm — narrative trigger
│   ├── roll.py         # !roll — direct dice call
│   ├── inventory.py    # !inventory — direct lib call
│   ├── status.py       # !status — direct lib call
│   ├── session.py      # !session-start, !session-end
│   └── join.py         # !join — player registration
└── requirements.txt    # discord.py
```

Lives as a new top-level directory. Not a `.claude/modules/` module — it's an independent harness.

## Error Handling & Limits

| Scenario | Handling |
|----------|----------|
| Claude takes too long (>60s) | Bot posts "DM is thinking..." after 10s. Timeout at 120s with error message. |
| Claude Code session dies | Bot detects non-zero exit code, posts error, suggests `!session-start` |
| Bot crashes mid-session | Campaign state safe in JSON. Restart bot, `!session-start` to resume. |
| Player not registered | Bot replies "Use `!join <character_name>` first" |
| Command in wrong channel | Bot ignores messages outside configured channel |
| Multiple `!dm` at once | Queue — one Claude invocation at a time, "Wait for the DM..." for extras |

**Rate limiting:** One Claude invocation at a time. Subsequent `!dm` commands queue.

**Message buffer overflow:** Rolling window of 50. Older messages drop off — they're in the persistent session context anyway.

## Scope Boundaries (Not Building)

- No web dashboard — Discord is the only interface
- No voice channel integration — text only
- No concurrent campaigns — one campaign, one channel
- No DM override/admin commands — Claude is sole DM
- No automated scheduling — sessions manually started/ended
- No image generation — maps, character art out of scope
- No modifications to existing CLI flow — `/dm` keeps working as-is
- No migration of CLI to multi-character — multi-character scoped to Discord only

## Dependencies

- `discord.py` — Discord bot framework
- `claude` CLI — already installed (user's Anthropic subscription)
- Existing `lib/` Python managers — called directly for mechanical commands
- Existing `tools/` bash scripts — called by Claude during narrative commands
