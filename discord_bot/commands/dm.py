"""!dm and !process commands -- send prompts to Claude via the bridge."""

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone

import discord
from discord_bot.commands import register
from discord_bot.response_router import route_response

_CONFIRM = "✅"
_DENY = "❌"
_ACTIVITY_WINDOW = timedelta(minutes=15)

DISCORD_MSG_LIMIT = 2000
PRIVATE_WHISPER_CHANCE = 0.1  # 20% chance to inject a private whisper prompt
log = logging.getLogger("dm_bot.commands")


def _maybe_inject_private_prompt(payload: str, player_map, *, exclude_character: str = "") -> str:
    """With random probability, append an instruction for Claude to whisper to a random player.

    Picks a character at random (excluding the active player to keep it
    interesting) and asks Claude to add a [PRIVATE:name] block with something
    only that character would notice — a sensory detail, a memory, a hunch.
    """
    if random.random() > PRIVATE_WHISPER_CHANCE:
        return payload

    all_players = player_map.get_all()
    if not all_players:
        return payload

    candidates = [
        data["character"] for data in all_players.values()
        if data["character"] != exclude_character
    ]
    # Fall back to full list if only one player
    if not candidates:
        candidates = [data["character"] for data in all_players.values()]

    target = random.choice(candidates)
    log.info("Injecting private whisper prompt for %r", target)

    payload += (
        f"\n\n[SYSTEM INSTRUCTION — private aside]"
        f"\nSomewhere in your response, include a [PRIVATE:{target}]...[/PRIVATE] block "
        f"with a short personal detail only {target} would notice — "
        f"a gut feeling, a half-remembered scent, a flicker in the shadows, "
        f"or something tied to their backstory. Keep it brief and atmospheric (1-3 sentences)."
    )
    return payload


async def _dispatch_whispers(whispers, player_map, client, channel) -> None:
    """Send whisper DMs to players and post channel acknowledgements."""
    for char_name, whisper_text in whispers:
        user_id = player_map.get_user_id_by_character(char_name)
        if user_id is None:
            log.warning("No player mapped to character %r — skipping whisper", char_name)
            continue
        try:
            user = await client.fetch_user(int(user_id))
            for i in range(0, len(whisper_text), DISCORD_MSG_LIMIT):
                await user.send(whisper_text[i:i + DISCORD_MSG_LIMIT])
            await channel.send(f"🤫 *The DM whispers to {char_name}...*")
        except discord.Forbidden:
            log.warning("Cannot DM character %r — DMs disabled", char_name)
            await channel.send(
                f"{char_name}, your DMs are closed — enable them to receive private messages."
            )


async def _resolve_player(message, ctx):
    """Return (discord_name, character) or send an error and return None."""
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id)
    if character is None:
        await message.channel.send("You're not registered. Use `!join <character_name>` first.")
        return None
    if not ctx.claude_bridge.is_active:
        await message.channel.send("No active session. Use `!session-start` first.")
        return None
    discord_name = ctx.player_map.get_discord_name(user_id)
    return discord_name, character


@register("dm")
async def handle_dm(message, args: str, ctx) -> None:
    """Handle !dm <text> -- ask the DM a question without advancing the plot."""
    result = await _resolve_player(message, ctx)
    if result is None:
        return
    discord_name, character = result

    log.info("!dm from %s (%s): %r", discord_name, character, args[:50] if args else "")

    payload = ctx.message_buffer.format_for_claude(
        [],
        active_player=discord_name,
        active_character=character,
        command_text=args,
        advance_plot=False,
    )
    log.debug("Payload built (%d chars), no buffer included", len(payload))

    thinking_msg = await message.channel.send("*The DM is thinking...*")
    try:
        response = await ctx.claude_bridge.send(payload)
        routed = route_response(response)

        if routed.public:
            for i in range(0, len(routed.public), DISCORD_MSG_LIMIT):
                await message.channel.send(routed.public[i:i + DISCORD_MSG_LIMIT])

        await _dispatch_whispers(routed.whispers, ctx.player_map, ctx.client, message.channel)
    except TimeoutError:
        log.warning("Claude timed out for !dm from %s", discord_name)
        await message.channel.send("The DM took too long to respond. Try again or `!session-start` to restart.")
    except RuntimeError as e:
        log.error("Claude error for !dm from %s: %s", discord_name, e)
        await message.channel.send(f"DM error: {e}")
    finally:
        await thinking_msg.delete()


async def _advance_plot(message, args: str, ctx) -> None:
    """Format buffer, send to Claude, route response."""
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
    """Handle !process <text> -- advance the plot; asks active players to confirm first."""
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

    if ctx.progress_pending:
        await message.channel.send("A progress confirmation is already pending.")
        return

    user_id = str(message.author.id)
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
    try:
        confirm_msg = await message.channel.send(confirm_text)
        try:
            await confirm_msg.add_reaction(_CONFIRM)
            await confirm_msg.add_reaction(_DENY)
        except Exception:
            pass

        confirmed: set[str] = set()
        deadline = asyncio.get_running_loop().time() + timeout_sec

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
    finally:
        ctx.progress_pending = False

    if not aborted:
        await _advance_plot(message, args, ctx)
