# Private DM Conversations Design Spec

## Overview

Extend the Discord bot so players can have multi-turn private conversations with the DM by directly DMing the bot. Players can ask about mechanics, their character, or propose secret actions. The DM (Claude) enforces guardrails (no spoilers, no plot advancement). Observable outcomes are published to the main channel via `[PUBLIC]` markers when the conversation ends.

This builds on the existing one-shot `!private` command and `[PRIVATE:name]` whisper system (spec: `2026-04-07-discord-private-messages-design.md`).

## Goals

- Players DM the bot directly to start a private conversation — no command needed in the public channel
- Bot verifies the player's identity (character + campaign) before proceeding
- Multi-turn back-and-forth between player and DM in Discord DMs
- Player ends the conversation with `!done`; DM produces a `[PUBLIC]` summary of observable outcomes
- Other players see a named notification when someone enters/exits a private chat
- Multiple players can have simultaneous private conversations
- All private messages are serialized onto the main Claude session queue (no concurrency issues)
- When no session is active, a lightweight "lite mode" answers basic mechanics/character questions

## Architecture

```
Player DMs bot directly
     |
     v
bot.py on_message
     |
     +-- guild message? --> existing channel logic
     |
     +-- DM message? --> PrivateChatManager.handle_dm_message()
              |
              +-- new chat? --> verify player, notify channel, greet player
              |
              +-- ongoing? --> queue onto ClaudeBridge.send() (serialized via _lock)
              |
              +-- !done? --> wrap-up prompt to Claude, extract [PUBLIC], post to channel
              |
              +-- no session? --> lite mode (one-shot, no session)
```

## Components

### 1. PrivateChatManager (`discord_bot/private_chat.py`)

Manages per-player private chat state. Lives on `BotContext`.

**State per player** (dict keyed by `user_id`):
```python
@dataclass
class PrivateChat:
    character: str
    discord_name: str
    status: str  # "active"
    message_count: int
```

No entry = idle (no active chat).

**Methods:**
- `handle_dm_message(message, ctx)` — main entry point for all DMs from players. Routes to start/continue/done logic.
- `start_chat(user_id, character, discord_name)` — creates state entry
- `end_chat(user_id)` — removes state entry
- `is_active(user_id)` — checks if player has an active chat
- `get_active_chats()` — returns all active chats (for injecting notes into `!process`)

### 2. DM Listener (`bot.py` changes)

Add DM detection to `on_message` before the channel filter:

```python
@client.event
async def on_message(message):
    if message.author.bot:
        return
    # DM check — no guild means it's a direct message
    if message.guild is None:
        await ctx.private_chat_manager.handle_dm_message(message, ctx)
        return
    # Existing channel logic
    result = on_message_handler(message, ctx)
    if result == "command":
        await dispatch_command(message, ctx)
```

**Main channel reference:** Store the main channel object on `BotContext` during `on_ready`:
```python
ctx.main_channel = client.get_channel(ctx.channel_id)
```

### 3. Claude Prompt Framing

All private chat messages are sent to the main Claude session via `claude_bridge.send()`, which already serializes with its `asyncio.Lock`.

**First message (chat start):**
```
[PRIVATE CONVERSATION with {character} ({discord_name})]
The player has initiated a private conversation with you.
Rules: No spoilers. No changes outside their character. Do not advance
the main plot. The player may propose a secret action — discuss it with
them privately. When the conversation ends, you will be asked to provide
a [PUBLIC] summary of any observable outcomes.

{character} says: {message_content}
[/PRIVATE CONVERSATION]
```

**Subsequent messages:**
```
[PRIVATE CONVERSATION with {character} continues]
{character} says: {message_content}
[/PRIVATE CONVERSATION]
```

**On `!done`:**
```
[PRIVATE CONVERSATION with {character} — ENDING]
The player is ending the private conversation. Wrap up and include a
[PUBLIC]...[/PUBLIC] block with anything the other players would observe
or notice as a result. If nothing observable happened, the [PUBLIC] block
can be empty or omitted. Frame the [PUBLIC] content however makes
narrative sense — you decide whether to attribute it.
[/PRIVATE CONVERSATION]
```

**Injection into `!process` payloads** — when one or more private chats are active, append to the process payload:
```
[NOTE: {character} is currently in a private conversation with the DM.
You may hold back on advancing events that would directly involve them,
or narrate around their temporary absence.]
```
One note per active private chat.

### 4. Response Router — `[PUBLIC]` Marker (`response_router.py`)

Add a `[PUBLIC]...[/PUBLIC]` regex pattern alongside the existing `[PRIVATE:name]` pattern.

**Extended dataclass:**
```python
@dataclass
class RoutedResponse:
    public: str
    whispers: list[tuple[str, str]] = field(default_factory=list)
    public_announcements: list[str] = field(default_factory=list)
```

- `public_announcements` contains extracted `[PUBLIC]` content
- `[PUBLIC]` blocks are removed from `public` (which goes back as a DM reply to the player)
- Processing order: strip `[MENTAL MODEL]`, extract `[PUBLIC]`, extract `[PRIVATE:name]`, remainder is `public`

### 5. Lite Mode — No Active Session

When `claude_bridge.is_active` is `False` and a player DMs the bot:

- No state tracked, no `!done` needed — each message is independent
- No notification posted to the main channel
- No `[PUBLIC]` routing
- Runs a **one-shot** `claude --print` call with a minimal prompt containing:
  - Player's character JSON (from `characters/{name}.json`)
  - Basic campaign info (name, current location from `campaign-overview.json`)
  - The player's message
  - Instruction: "Answer mechanics, spells, inventory, and character questions only. No plot advancement, no narrative."

**Player indication:** When responding in lite mode, the bot prefixes its first reply with: *"(No active session — I can answer basic mechanics and character questions.)"* so the player knows the scope is limited.

**New method on ClaudeBridge:**
```python
async def send_oneshot(self, prompt: str, timeout: float = 60.0) -> str:
    """Run a single prompt without a session. For lite-mode queries."""
```
Builds `claude --print <prompt>` without `--session-id` or `--resume`.

### 6. Channel Notifications

**When a private chat starts:**
Post to main channel: `*{character} pulls the DM aside for a private word...*`

**When a private chat ends (`!done`):**
Post to main channel: `*{character} returns to the group.*`
Followed by any `[PUBLIC]` content from Claude's wrap-up response.

**When `!done` produces no `[PUBLIC]` content:**
Just the return notification, no additional post.

## Message Flow Examples

### Example 1: Secret Action

```
[DM] Andraxxus: Can I walk towards that angry NPC and whisper that
                if he joins our party, he gets all the gold?
  → channel: "*Andraxxus pulls the DM aside for a private word...*"
  → DM reply: "Interesting approach. The NPC is Graal, a mercenary.
               Roll a Persuasion check... You rolled 17. He's
               listening. What exactly do you offer?"

[DM] Andraxxus: All the gold from our next job. I'll whisper it
                so the others can't hear.
  → DM reply: "Graal raises an eyebrow. He mutters back: 'All of it?
               You've got yourself a deal, stranger.' He extends
               a scarred hand."

[DM] Andraxxus: !done
  → DM reply: "The deal is struck. Graal will keep your arrangement
               to himself — for now."
  → channel: "*Andraxxus returns to the group.*"
  → channel: "The angry NPC's expression softens. He sheathes his
              blade and nods slowly. 'Fine. I'll travel with you —
              for now.'"
```

### Example 2: Mechanics Question (No Session)

```
[DM] Andraxxus: What spells do I have prepared?
  → DM reply: (lite mode, one-shot) "Based on your character sheet,
               you have the following spells prepared: ..."
  → No channel notification
```

### Example 3: Concurrent Private Chats

```
[DM] Andraxxus: (starts private chat)
  → channel: "*Andraxxus pulls the DM aside...*"
[DM] Wielundor: (starts private chat)
  → channel: "*Wielundor pulls the DM aside...*"
[Public] !process the remaining party members set up camp
  → Claude sees notes about both absent players
  → Narrates camp setup without Andraxxus/Wielundor
[DM] Andraxxus: !done
  → channel: "*Andraxxus returns to the group.*" + [PUBLIC] content
[DM] Wielundor: !done
  → channel: "*Wielundor returns to the group.*" + [PUBLIC] content
```

## Error Handling

| Scenario | Handling |
|----------|----------|
| DM from unknown user | Reply in DM: "I don't recognize you. Use `!join <character_name>` in the game channel first." |
| `!done` with no active chat | Reply in DM: "You don't have an active private conversation." |
| Claude timeout during private chat | Reply in DM with timeout message. Chat stays active so player can retry. |
| Bot restart during active chat | State lost (ephemeral). Player starts a new DM. No recovery needed. |
| Main channel unreachable | Log warning, skip channel notifications. DM conversation still works. |
| `!done` while previous message still processing | `ClaudeBridge._lock` handles this — `!done` waits in queue until previous send completes. |

## Scope Boundaries (Not Building)

- No persistent private chat history across bot restarts
- No group private conversations (multiple players in one private thread)
- No player-to-player private messaging via bot
- No turn limits — DM (Claude) manages pacing naturally
- No changes to the existing one-shot `!private` command (it continues to work as-is)
