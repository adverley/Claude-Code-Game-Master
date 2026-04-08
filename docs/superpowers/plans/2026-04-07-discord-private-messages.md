# Discord Private Messages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add private DM support to the Discord bot: players can use `!private <msg>` to get a private Claude response, and Claude can proactively whisper to individual players using `[PRIVATE:character]...[/PRIVATE]` markers.

**Architecture:** A new `ResponseRouter` parses `[PRIVATE:name]` markers from Claude responses and splits them into public text and per-character whispers. Both `!dm`/`!process` (DM-initiated) and `!private` (player-initiated) route through this. The Discord bot DMes whispers via `ctx.client.fetch_user()`.

**Tech Stack:** Python, discord.py, pytest-asyncio, existing `discord_bot/` package

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| `discord_bot/response_router.py` | Create | `RoutedResponse` dataclass + `route_response()` parser |
| `discord_bot/player_map.py` | Modify | Add `get_user_id_by_character()` reverse lookup |
| `discord_bot/bot.py` | Modify | Add `client: discord.Client` field to `BotContext` |
| `discord_bot/commands/dm.py` | Modify | Route response through `ResponseRouter`; send whispers via `ctx.client` |
| `discord_bot/commands/private.py` | Create | `!private` command — DMs full response to requesting player |
| `discord_bot/commands/__init__.py` | Modify | Import `private` to trigger registration |
| `discord_bot/claude_bridge.py` | Modify | Add `[PRIVATE:name]` instruction to session init prompt |
| `tests/test_discord/test_response_router.py` | Create | Unit tests for `route_response()` |
| `tests/test_discord/test_player_map.py` | Modify | Tests for `get_user_id_by_character()` |
| `tests/test_discord/test_private_command.py` | Create | Tests for `!private` command |
| `tests/test_discord/test_dm_command.py` | Modify | Add whisper routing tests |

---

## Task 1: ResponseRouter

**Files:**
- Create: `discord_bot/response_router.py`
- Create: `tests/test_discord/test_response_router.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_discord/test_response_router.py`:

```python
import pytest
from discord_bot.response_router import route_response, RoutedResponse


class TestRouteResponse:
    def test_no_markers_returns_full_text_as_public(self):
        result = route_response("You find a hidden door.")
        assert result.public == "You find a hidden door."
        assert result.whispers == []

    def test_single_marker_extracted_to_whisper(self):
        text = "The party enters the tavern.[PRIVATE:thorin]You recognise the barkeep as an old enemy.[/PRIVATE]"
        result = route_response(text)
        assert result.public == "The party enters the tavern."
        assert result.whispers == [("thorin", "You recognise the barkeep as an old enemy.")]

    def test_multiple_markers_to_different_characters(self):
        text = "[PRIVATE:thorin]The map is fake.[/PRIVATE]The group presses on.[PRIVATE:elara]You sense illusion magic.[/PRIVATE]"
        result = route_response(text)
        assert result.public == "The group presses on."
        assert ("thorin", "The map is fake.") in result.whispers
        assert ("elara", "You sense illusion magic.") in result.whispers

    def test_marker_only_response_has_empty_public(self):
        text = "[PRIVATE:thorin]Just for you.[/PRIVATE]"
        result = route_response(text)
        assert result.public == ""
        assert result.whispers == [("thorin", "Just for you.")]

    def test_character_name_is_case_insensitive(self):
        text = "[PRIVATE:THORIN]A secret.[/PRIVATE]"
        result = route_response(text)
        assert result.whispers[0][0] == "THORIN"  # name preserved as-is from marker

    def test_multiline_content_in_marker(self):
        text = "[PRIVATE:thorin]Line one.\nLine two.\nLine three.[/PRIVATE]"
        result = route_response(text)
        assert result.whispers[0][1] == "Line one.\nLine two.\nLine three."

    def test_returns_routedresponse_instance(self):
        result = route_response("hello")
        assert isinstance(result, RoutedResponse)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_discord/test_response_router.py -v
```

Expected: `ImportError` — `response_router` does not exist yet.

- [ ] **Step 3: Implement ResponseRouter**

Create `discord_bot/response_router.py`:

```python
"""Parse [PRIVATE:name]...[/PRIVATE] markers from Claude responses."""

import re
from dataclasses import dataclass, field

_PRIVATE_RE = re.compile(r'\[PRIVATE:([^\]]+)\](.*?)\[/PRIVATE\]', re.DOTALL)


@dataclass
class RoutedResponse:
    public: str
    whispers: list[tuple[str, str]] = field(default_factory=list)


def route_response(text: str) -> RoutedResponse:
    """Split a Claude response into public text and per-character whispers.

    Any [PRIVATE:character_name]...[/PRIVATE] blocks are removed from the
    public text and returned as (character_name, content) tuples in whispers.
    """
    whispers: list[tuple[str, str]] = []

    def _extract(match: re.Match) -> str:
        character = match.group(1).strip()
        content = match.group(2).strip()
        whispers.append((character, content))
        return ""

    public = _PRIVATE_RE.sub(_extract, text).strip()
    return RoutedResponse(public=public, whispers=whispers)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_discord/test_response_router.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add discord_bot/response_router.py tests/test_discord/test_response_router.py
git commit -m "feat(discord): add ResponseRouter for [PRIVATE:name] marker parsing"
```

---

## Task 2: PlayerMap reverse lookup

**Files:**
- Modify: `discord_bot/player_map.py`
- Modify: `tests/test_discord/test_player_map.py`

- [ ] **Step 1: Write the failing tests**

Add to the `TestPlayerMap` class in `tests/test_discord/test_player_map.py`:

```python
    def test_get_user_id_by_character_found(self, tmp_path):
        path = make_player_map_file(tmp_path, {
            "players": {
                "111": {"discord_name": "Erik", "character": "thorin"},
                "222": {"discord_name": "Sara", "character": "elara"},
            }
        })
        pm = PlayerMap(path)
        assert pm.get_user_id_by_character("thorin") == "111"
        assert pm.get_user_id_by_character("elara") == "222"

    def test_get_user_id_by_character_case_insensitive(self, tmp_path):
        path = make_player_map_file(tmp_path, {
            "players": {"111": {"discord_name": "Erik", "character": "thorin"}}
        })
        pm = PlayerMap(path)
        assert pm.get_user_id_by_character("THORIN") == "111"
        assert pm.get_user_id_by_character("Thorin") == "111"

    def test_get_user_id_by_character_not_found(self, tmp_path):
        path = make_player_map_file(tmp_path, {"players": {}})
        pm = PlayerMap(path)
        assert pm.get_user_id_by_character("nobody") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_discord/test_player_map.py -v
```

Expected: 3 new tests FAIL with `AttributeError: 'PlayerMap' object has no attribute 'get_user_id_by_character'`.

- [ ] **Step 3: Implement the method**

Add after the `get_discord_name` method in `discord_bot/player_map.py`:

```python
    def get_user_id_by_character(self, character_name: str) -> Optional[str]:
        """Reverse lookup: character name → Discord user ID. Case-insensitive."""
        name = character_name.lower()
        for user_id, data in self._data["players"].items():
            if data["character"].lower() == name:
                return user_id
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_discord/test_player_map.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add discord_bot/player_map.py tests/test_discord/test_player_map.py
git commit -m "feat(discord): add PlayerMap.get_user_id_by_character() reverse lookup"
```

---

## Task 3: Add client to BotContext

**Files:**
- Modify: `discord_bot/bot.py`

- [ ] **Step 1: Add `client` field to `BotContext`**

In `discord_bot/bot.py`, change the `BotContext` dataclass from:

```python
@dataclass
class BotContext:
    """Shared state passed to all command handlers."""
    config: dict
    message_buffer: MessageBuffer
    claude_bridge: ClaudeBridge
    player_map: PlayerMap
    channel_id: int
```

to:

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
```

- [ ] **Step 2: Pass client when constructing BotContext**

In `discord_bot/bot.py`, in the `main()` function, update the `BotContext` construction (currently at the end of `main()`, before `@client.event`) to set `client` after the client is created. Change:

```python
    ctx = BotContext(
        config=config,
        message_buffer=MessageBuffer(max_size=config["message_buffer_size"]),
        claude_bridge=ClaudeBridge(project_dir=str(PROJECT_DIR), model=model, claude_debug=args.claude_debug),
        player_map=PlayerMap(player_map_path),
        channel_id=int(config["channel_id"]),
    )
```

to:

```python
    ctx = BotContext(
        config=config,
        message_buffer=MessageBuffer(max_size=config["message_buffer_size"]),
        claude_bridge=ClaudeBridge(project_dir=str(PROJECT_DIR), model=model, claude_debug=args.claude_debug),
        player_map=PlayerMap(player_map_path),
        channel_id=int(config["channel_id"]),
        client=client,
    )
```

- [ ] **Step 3: Run existing tests to confirm nothing broke**

```bash
uv run pytest tests/test_discord/ -v
```

Expected: all existing tests PASS.

- [ ] **Step 4: Commit**

```bash
git add discord_bot/bot.py
git commit -m "feat(discord): add client field to BotContext for DM sending"
```

---

## Task 4: !private command

**Files:**
- Create: `discord_bot/commands/private.py`
- Modify: `discord_bot/commands/__init__.py`
- Create: `tests/test_discord/test_private_command.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_discord/test_private_command.py`:

```python
import pytest
import discord
from unittest.mock import AsyncMock, MagicMock
from discord_bot.commands.private import handle_private


class FakeMessage:
    def __init__(self, user_id="111", display_name="Erik"):
        self.author = MagicMock()
        self.author.id = user_id
        self.author.display_name = display_name
        self.channel = MagicMock()
        self.channel.send = AsyncMock()


class FakeCtx:
    def __init__(self, character="thorin", discord_name="Erik"):
        self.player_map = MagicMock()
        self.player_map.get_character.return_value = character
        self.player_map.get_discord_name.return_value = discord_name
        self.message_buffer = MagicMock()
        self.message_buffer.format_for_claude.return_value = "[Discord context]\nActive player: Erik (thorin)\nQuestion: secret"
        self.config = {}
        self.claude_bridge = AsyncMock()
        self.claude_bridge.is_active = True
        self.claude_bridge.send = AsyncMock(return_value="Only you know the truth about the amulet.")
        mock_user = AsyncMock()
        mock_user.send = AsyncMock()
        self.client = AsyncMock()
        self.client.fetch_user = AsyncMock(return_value=mock_user)


@pytest.mark.asyncio
class TestPrivateCommand:
    async def test_dms_response_to_player(self):
        msg = FakeMessage()
        ctx = FakeCtx()

        await handle_private(msg, "what do I know about the amulet?", ctx)

        ctx.client.fetch_user.assert_called_once_with(int("111"))
        dm_user = ctx.client.fetch_user.return_value
        dm_user.send.assert_called_once()
        dm_text = dm_user.send.call_args[0][0]
        assert "amulet" in dm_text

    async def test_posts_whisper_ack_to_channel(self):
        msg = FakeMessage()
        ctx = FakeCtx()

        await handle_private(msg, "my secret question", ctx)

        channel_calls = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("whispers" in c.lower() or "🤫" in c for c in channel_calls)

    async def test_rejects_unregistered_player(self):
        msg = FakeMessage()
        ctx = FakeCtx(character=None)

        await handle_private(msg, "secret", ctx)

        ctx.claude_bridge.send.assert_not_called()
        sent_text = msg.channel.send.call_args[0][0]
        assert "!join" in sent_text

    async def test_rejects_when_no_session(self):
        msg = FakeMessage()
        ctx = FakeCtx()
        ctx.claude_bridge.is_active = False

        await handle_private(msg, "secret", ctx)

        ctx.claude_bridge.send.assert_not_called()
        sent_text = msg.channel.send.call_args[0][0]
        assert "session-start" in sent_text

    async def test_handles_dms_disabled(self):
        msg = FakeMessage()
        ctx = FakeCtx()
        forbidden_response = MagicMock()
        forbidden_response.status = 403
        forbidden_response.reason = "Forbidden"
        dm_user = AsyncMock()
        dm_user.send.side_effect = discord.Forbidden(forbidden_response, "Cannot send messages to this user")
        ctx.client.fetch_user = AsyncMock(return_value=dm_user)

        await handle_private(msg, "secret", ctx)

        channel_calls = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("DMs are closed" in c or "enable" in c.lower() for c in channel_calls)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_discord/test_private_command.py -v
```

Expected: `ImportError` — `private` module does not exist yet.

- [ ] **Step 3: Implement the !private command**

Create `discord_bot/commands/private.py`:

```python
"""!private command -- ask the DM something privately."""

import logging
import discord
from discord_bot.commands import register

DISCORD_MSG_LIMIT = 2000
log = logging.getLogger("dm_bot.commands")


@register("private")
async def handle_private(message, args: str, ctx) -> None:
    """Handle !private <text> -- Claude responds privately via DM."""
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id)
    if character is None:
        await message.channel.send("You're not registered. Use `!join <character_name>` first.")
        return
    if not ctx.claude_bridge.is_active:
        await message.channel.send("No active session. Use `!session-start` first.")
        return
    discord_name = ctx.player_map.get_discord_name(user_id)

    payload = ctx.message_buffer.format_for_claude(
        [],
        active_player=discord_name,
        active_character=character,
        command_text=args,
        advance_plot=False,
    )
    payload += "\n\n[This is a private message to this player only — do not address the full party.]"

    log.info("!private from %s (%s): %r", discord_name, character, args[:50] if args else "")

    thinking_msg = await message.channel.send("*The DM is thinking...*")
    try:
        response = await ctx.claude_bridge.send(payload)
        await thinking_msg.delete()

        try:
            user = await ctx.client.fetch_user(int(user_id))
            for i in range(0, len(response), DISCORD_MSG_LIMIT):
                await user.send(response[i:i + DISCORD_MSG_LIMIT])
            await message.channel.send(f"🤫 *The DM whispers to {character}...*")
        except discord.Forbidden:
            log.warning("Cannot DM %s (%s) — DMs disabled", discord_name, character)
            await message.channel.send(
                f"{character}, your DMs are closed — enable them to receive private messages."
            )
    except TimeoutError:
        log.warning("Claude timed out for !private from %s", discord_name)
        await thinking_msg.delete()
        await message.channel.send("The DM took too long to respond. Try again or `!session-start` to restart.")
    except RuntimeError as e:
        log.error("Claude error for !private from %s: %s", discord_name, e)
        await thinking_msg.delete()
        await message.channel.send(f"DM error: {e}")
```

- [ ] **Step 4: Register the command**

In `discord_bot/commands/__init__.py`, add `private` to the import line at the bottom:

```python
from discord_bot.commands import dm, roll, inventory, status, session, join, help_cmd, overview, save, private  # noqa: E402, F401
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_discord/test_private_command.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add discord_bot/commands/private.py discord_bot/commands/__init__.py tests/test_discord/test_private_command.py
git commit -m "feat(discord): add !private command for player-initiated DMs"
```

---

## Task 5: Route !dm and !process through ResponseRouter

**Files:**
- Modify: `discord_bot/commands/dm.py`
- Modify: `tests/test_discord/test_dm_command.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_discord/test_dm_command.py`:

```python
import discord
from discord_bot.commands.dm import handle_dm


class FakeCtxWithClient(FakeCtx):
    def __init__(self, character="thorin", discord_name="Erik"):
        super().__init__(character, discord_name)
        mock_dm_user = AsyncMock()
        mock_dm_user.send = AsyncMock()
        self.client = AsyncMock()
        self.client.fetch_user = AsyncMock(return_value=mock_dm_user)
        self.player_map.get_user_id_by_character = MagicMock(return_value="111")


@pytest.mark.asyncio
class TestDmCommandRouting:
    async def test_public_text_posted_to_channel(self):
        msg = FakeMessage()
        ctx = FakeCtxWithClient()
        ctx.claude_bridge.send = AsyncMock(return_value="The door creaks open.")

        await handle_dm(msg, "I open the door", ctx)

        calls = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("door" in c for c in calls)

    async def test_private_marker_sends_dm_not_channel(self):
        msg = FakeMessage()
        ctx = FakeCtxWithClient()
        ctx.claude_bridge.send = AsyncMock(
            return_value="The party moves on.[PRIVATE:thorin]You notice a trapdoor.[/PRIVATE]"
        )

        await handle_dm(msg, "we enter the room", ctx)

        # Channel should NOT contain the private text
        channel_calls = [c[0][0] for c in msg.channel.send.call_args_list]
        assert not any("trapdoor" in c for c in channel_calls)

        # DM user should receive the private text
        dm_user = ctx.client.fetch_user.return_value
        dm_calls = [c[0][0] for c in dm_user.send.call_args_list]
        assert any("trapdoor" in c for c in dm_calls)

    async def test_whisper_ack_posted_to_channel(self):
        msg = FakeMessage()
        ctx = FakeCtxWithClient()
        ctx.claude_bridge.send = AsyncMock(
            return_value="[PRIVATE:thorin]Secret message.[/PRIVATE]"
        )

        await handle_dm(msg, "anything", ctx)

        channel_calls = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("🤫" in c or "whispers" in c.lower() for c in channel_calls)

    async def test_unknown_character_in_marker_skips_silently(self):
        msg = FakeMessage()
        ctx = FakeCtxWithClient()
        ctx.player_map.get_user_id_by_character = MagicMock(return_value=None)
        ctx.claude_bridge.send = AsyncMock(
            return_value="[PRIVATE:nobody]Secret.[/PRIVATE]Public text."
        )

        await handle_dm(msg, "anything", ctx)

        # Should not crash; public text still posted
        channel_calls = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("Public text" in c for c in channel_calls)

    async def test_dms_disabled_posts_channel_error(self):
        msg = FakeMessage()
        ctx = FakeCtxWithClient()
        ctx.claude_bridge.send = AsyncMock(
            return_value="[PRIVATE:thorin]Secret.[/PRIVATE]"
        )
        forbidden_response = MagicMock()
        forbidden_response.status = 403
        forbidden_response.reason = "Forbidden"
        dm_user = AsyncMock()
        dm_user.send.side_effect = discord.Forbidden(forbidden_response, "Cannot send")
        ctx.client.fetch_user = AsyncMock(return_value=dm_user)

        await handle_dm(msg, "anything", ctx)

        channel_calls = [c[0][0] for c in msg.channel.send.call_args_list]
        assert any("DMs are closed" in c or "enable" in c.lower() for c in channel_calls)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_discord/test_dm_command.py -v
```

Expected: new routing tests FAIL (`AttributeError` on `ctx.client` since `handle_dm` doesn't use it yet).

- [ ] **Step 3: Update dm.py to route through ResponseRouter**

Replace the response-posting block in `handle_dm` (the `try:` block starting at line 71) with:

```python
import discord
from discord_bot.response_router import route_response
```

Add these imports at the top of `discord_bot/commands/dm.py` (after existing imports).

Then replace the `try:` block in `handle_dm` (lines 71–84) with:

```python
    thinking_msg = await message.channel.send("*The DM is thinking...*")
    try:
        response = await ctx.claude_bridge.send(payload)
        await thinking_msg.delete()
        routed = route_response(response)

        if routed.public:
            for i in range(0, len(routed.public), DISCORD_MSG_LIMIT):
                await message.channel.send(routed.public[i:i + DISCORD_MSG_LIMIT])

        for char_name, whisper_text in routed.whispers:
            user_id = ctx.player_map.get_user_id_by_character(char_name)
            if user_id is None:
                log.warning("No player mapped to character %r — skipping whisper", char_name)
                continue
            try:
                user = await ctx.client.fetch_user(int(user_id))
                for i in range(0, len(whisper_text), DISCORD_MSG_LIMIT):
                    await user.send(whisper_text[i:i + DISCORD_MSG_LIMIT])
                await message.channel.send(f"🤫 *The DM whispers to {char_name}...*")
            except discord.Forbidden:
                log.warning("Cannot DM character %r — DMs disabled", char_name)
                await message.channel.send(
                    f"{char_name}, your DMs are closed — enable them to receive private messages."
                )
    except TimeoutError:
        log.warning("Claude timed out for !dm from %s", discord_name)
        await thinking_msg.delete()
        await message.channel.send("The DM took too long to respond. Try again or `!session-start` to restart.")
    except RuntimeError as e:
        log.error("Claude error for !dm from %s: %s", discord_name, e)
        await thinking_msg.delete()
        await message.channel.send(f"DM error: {e}")
```

Apply the same routing logic to `handle_process` — replace its `try:` block (lines 113–128) with an identical structure, keeping the `finally: ctx.message_buffer.mark_sent()` at the end:

```python
    thinking_msg = await message.channel.send("*The DM is thinking...*")
    try:
        response = await ctx.claude_bridge.send(payload)
        await thinking_msg.delete()
        routed = route_response(response)

        if routed.public:
            for i in range(0, len(routed.public), DISCORD_MSG_LIMIT):
                await message.channel.send(routed.public[i:i + DISCORD_MSG_LIMIT])

        for char_name, whisper_text in routed.whispers:
            user_id = ctx.player_map.get_user_id_by_character(char_name)
            if user_id is None:
                log.warning("No player mapped to character %r — skipping whisper", char_name)
                continue
            try:
                user = await ctx.client.fetch_user(int(user_id))
                for i in range(0, len(whisper_text), DISCORD_MSG_LIMIT):
                    await user.send(whisper_text[i:i + DISCORD_MSG_LIMIT])
                await message.channel.send(f"🤫 *The DM whispers to {char_name}...*")
            except discord.Forbidden:
                log.warning("Cannot DM character %r — DMs disabled", char_name)
                await message.channel.send(
                    f"{char_name}, your DMs are closed — enable them to receive private messages."
                )
    except TimeoutError:
        log.warning("Claude timed out for !process from %s", discord_name)
        await thinking_msg.delete()
        await message.channel.send("The DM took too long to respond. Try again or `!session-start` to restart.")
    except RuntimeError as e:
        log.error("Claude error for !process from %s: %s", discord_name, e)
        await thinking_msg.delete()
        await message.channel.send(f"DM error: {e}")
    finally:
        ctx.message_buffer.mark_sent()
        log.debug("Message buffer marked sent")
```

- [ ] **Step 4: Update existing FakeCtx in test_dm_command.py to include client**

The original `FakeCtx` (used by `TestDmCommand`) needs `client` and `get_user_id_by_character` so the existing tests don't break. In `tests/test_discord/test_dm_command.py`, update `FakeCtx`:

```python
class FakeCtx:
    def __init__(self, character="thorin", discord_name="Erik"):
        self.player_map = MagicMock()
        self.player_map.get_character.return_value = character
        self.player_map.get_discord_name.return_value = discord_name
        self.player_map.get_user_id_by_character = MagicMock(return_value=None)
        self.message_buffer = MagicMock()
        self.message_buffer.get_delta.return_value = [
            {"timestamp": "14:32", "discord_name": "Erik", "character_name": "thorin", "content": "let's go"}
        ]
        self.message_buffer.format_for_claude.return_value = "[Discord context]\nActive player: Erik (thorin)\nQuestion: I search"
        self.config = {}
        self.claude_bridge = AsyncMock()
        self.claude_bridge.is_active = True
        self.claude_bridge.send = AsyncMock(return_value="You find a hidden door behind the bookshelf.")
        mock_dm_user = AsyncMock()
        mock_dm_user.send = AsyncMock()
        self.client = AsyncMock()
        self.client.fetch_user = AsyncMock(return_value=mock_dm_user)
```

- [ ] **Step 5: Run all dm tests to verify they pass**

```bash
uv run pytest tests/test_discord/test_dm_command.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest tests/test_discord/ -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add discord_bot/commands/dm.py tests/test_discord/test_dm_command.py
git commit -m "feat(discord): route !dm and !process responses through ResponseRouter for whisper support"
```

---

## Task 6: Update session init prompt

**Files:**
- Modify: `discord_bot/claude_bridge.py`

- [ ] **Step 1: Add whisper instruction to init prompt**

In `discord_bot/claude_bridge.py`, update `_build_init_prompt` to append the `[PRIVATE]` instruction. Change the return statement from:

```python
        return (
            f"You are the DM for a Discord multi-player D&D session.\n"
            f"Campaign: {campaign}\n\n"
            f"Players:\n{player_block}\n\n"
            f"Each player has their own character file in characters/.\n"
            f"When a player acts, use their character for rolls and state changes.\n"
            f"You can update any character as needed (e.g. area damage hits everyone).\n\n"
            f"Start by running:\n"
            f"  bash tools/dm-session.sh start\n"
            f"  bash tools/dm-session.sh context\n\n"
            f"Then narrate the opening scene based on where the campaign left off.\n"
            f"Respond in character as the DM. Be vivid and engaging."
        )
```

to:

```python
        return (
            f"You are the DM for a Discord multi-player D&D session.\n"
            f"Campaign: {campaign}\n\n"
            f"Players:\n{player_block}\n\n"
            f"Each player has their own character file in characters/.\n"
            f"When a player acts, use their character for rolls and state changes.\n"
            f"You can update any character as needed (e.g. area damage hits everyone).\n\n"
            f"To send a private message to a specific player, wrap it in "
            f"[PRIVATE:character_name]...[/PRIVATE]. "
            f"Everything outside these markers is posted publicly to the channel.\n\n"
            f"Start by running:\n"
            f"  bash tools/dm-session.sh start\n"
            f"  bash tools/dm-session.sh context\n\n"
            f"Then narrate the opening scene based on where the campaign left off.\n"
            f"Respond in character as the DM. Be vivid and engaging."
        )
```

- [ ] **Step 2: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add discord_bot/claude_bridge.py
git commit -m "feat(discord): instruct Claude on [PRIVATE:name] whisper syntax in session init"
```
