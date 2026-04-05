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
