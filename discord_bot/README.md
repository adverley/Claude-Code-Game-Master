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
cd discord_bot
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
uv run python discord_bot/bot.py
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

1. Start with `!session-start` -- this launches a persistent Claude Code session
2. Everyone chats normally in the channel -- the bot tracks all messages for context
3. When someone wants the DM to act, they use `!dm <what they do>`
4. Claude receives the recent chat context and responds as DM
5. Mechanical commands (`!roll`, `!inventory`, `!status`) are instant -- no Claude needed
6. End with `!session-end` when you're done playing

## Character Setup

Each player needs a character JSON file in `world-state/campaigns/<name>/characters/`:

```json
{
  "name": "Thorin",
  "race": "Dwarf",
  "class": "Fighter",
  "level": 5,
  "hp": {"current": 45, "max": 50},
  "gold": 250,
  "xp": 12500,
  "equipment": ["Warhammer", "Shield", "Chain Mail"]
}
```

Then link your Discord account: `!join thorin`

---

## Architecture

The bot is an asyncio program (discord.py) that spawns the `claude` CLI as a subprocess and relays messages between Discord and Claude. All shared state lives on a single `BotContext` dataclass wired in `bot.py`.

```
Discord event (discord.py)
  │
  ├── DM channel ────→ PrivateChatManager.handle_dm_message(message, ctx)
  │                      ├── resolve_player            (commands/_helpers.py)
  │                      ├── build_*_prompt            (private_chat_prompts.py)
  │                      ├── ctx.claude_bridge.send / send_oneshot
  │                      └── send_chunked / send_claude_reply   (discord_utils.py)
  │
  └── Guild channel ─→ bot.on_message_handler
                         ├── track message → MessageBuffer
                         └── dispatch_command
                                │
                                ▼
                         commands/<name>.py :: handle_<name>
                           ├── resolve_player          (_helpers.py)
                           ├── (gated) claim_gate + run_confirmation_gate
                           ├── MessageBuffer.format_for_claude
                           ├── ctx.claude_bridge.send
                           ├── response_router.route_response
                           └── send_claude_reply       (discord_utils.py)
```

### Module responsibilities

| Module | Responsibility |
|---|---|
| `bot.py` | Entrypoint; wires `BotContext`; owns the on_ready / on_message handlers. |
| `_bootstrap.py` | One-time `sys.path` install so commands can import from `lib/` and `.claude/modules/*/lib`. |
| `config.py` | Load and validate `config.json`. |
| `claude_bridge.py` | Run the Claude CLI subprocess; owns `session_id`, init-vs-resume, and the async lock. |
| `message_buffer.py` | Rolling chat-context buffer; builds the Claude prompt envelope. |
| `player_map.py` | Discord-user-id ↔ character mapping; best-effort name matching. |
| `activity_tracker.py` | `last_seen` timestamps + `Pace` enum (confirmation-gate timeouts). |
| `response_router.py` | Parse `[PRIVATE:]` / `[PUBLIC]` / `[MENTAL MODEL]` from Claude replies. |
| `discord_utils.py` | `send_chunked`, `dispatch_whispers`, `send_claude_reply`. |
| `private_chat.py` | `PrivateChatManager` — owns which users have an open private chat + orchestrates their DM flow. |
| `private_chat_prompts.py` | Pure prompt-builders for private chats + lite-mode `load_lite_context`. |
| `commands/__init__.py` | Command registry decorator and argument parser. |
| `commands/_helpers.py` | `resolve_player`, `with_thinking`, `claim_gate`. |
| `commands/confirmation_gate.py` | Shared ✅/❌ vote primitive for gated actions. |
| `commands/<name>.py` | One file per user-visible command. |

### Message-passing rules

Three rules that keep the code legible — breaking them re-introduces the duplication the current structure is designed to eliminate.

1. **Every message to Discord goes through `discord_utils`.** Handlers never call `channel.send(long_text)` directly in a loop; use `send_chunked` or `send_claude_reply`.
2. **Every Claude response is parsed through `response_router.route_response` before anything is sent.** Handlers never substring-match or regex `[PRIVATE:]` themselves.
3. **Gated actions wrap `run_confirmation_gate` in `claim_gate(ctx, name)`** so only one instance of a given gate can be open at a time. Adding a new gated action means picking a name and nothing else on `BotContext`.

### Adding a new command

1. Create `discord_bot/commands/<name>.py`.
2. `@register("<name>")` on an `async def handle_<name>(message, args, ctx)` function.
3. Use `resolve_player(message, ctx, require_session=...)` if the command needs a known character or a live session.
4. If it calls Claude: wrap the subprocess call in `async with with_thinking(message.channel):` and send the reply via `send_claude_reply(routed, channel=..., player_map=ctx.player_map, client=ctx.client)`.
5. Add the module name to the import list in `commands/__init__.py`.

Do **not**: reach into `ctx.claude_bridge._project_dir` (use `.project_dir`), redeclare `DISCORD_MSG_LIMIT`, duplicate the chunking loop, import helpers from sibling command files, or add bespoke `pending_foo` booleans to `BotContext` (use `claim_gate`).

### Tests

`uv run pytest tests/test_discord/` — the Discord-specific suite. The same helpers are imported directly by tests, so behavioral regressions in `discord_utils`, `_helpers`, or `private_chat_prompts` are caught without touching any real Discord connection.
