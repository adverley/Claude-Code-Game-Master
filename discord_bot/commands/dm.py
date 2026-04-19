"""!dm and !process commands -- send prompts to Claude via the bridge."""

import logging
import random

from discord_bot.commands import register
from discord_bot.commands._helpers import GateBusy, claim_gate, resolve_player, with_thinking
from discord_bot.commands.confirmation_gate import _CONFIRM, _DENY, get_active_candidates, run_confirmation_gate
from discord_bot.discord_utils import send_claude_reply
from discord_bot.response_router import route_response

PRIVATE_WHISPER_CHANCE = 0.1
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


@register("dm")
async def handle_dm(message, args: str, ctx) -> None:
    """Handle !dm <text> -- ask the DM a question without advancing the plot."""
    player = await resolve_player(message, ctx, require_session=True)
    if player is None:
        return

    log.info("!dm from %s (%s): %r", player.discord_name, player.character, args[:50] if args else "")

    payload = ctx.message_buffer.format_for_claude(
        [],
        active_player=player.discord_name,
        active_character=player.character,
        command_text=args,
        advance_plot=False,
    )
    log.debug("Payload built (%d chars), no buffer included", len(payload))

    async with with_thinking(message.channel):
        try:
            response = await ctx.claude_bridge.send(payload)
            routed = route_response(response)
            await send_claude_reply(routed, channel=message.channel,
                                    player_map=ctx.player_map, client=ctx.client)
        except TimeoutError:
            log.warning("Claude timed out for !dm from %s", player.discord_name)
            await message.channel.send("The DM took too long to respond. Try again or `!session-start` to restart.")
        except RuntimeError as e:
            log.error("Claude error for !dm from %s: %s", player.discord_name, e)
            await message.channel.send(f"DM error: {e}")


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

    async with with_thinking(message.channel):
        try:
            response = await ctx.claude_bridge.send(payload)
            routed = route_response(response)
            await send_claude_reply(routed, channel=message.channel,
                                    player_map=ctx.player_map, client=ctx.client)
        except TimeoutError:
            log.warning("Claude timed out for plot advancement from %s", message.author.display_name)
            await message.channel.send("The DM took too long to respond. Try again or `!session-start` to restart.")
        except RuntimeError as e:
            log.error("Claude error for plot advancement from %s: %s", message.author.display_name, e)
            await message.channel.send(f"DM error: {e}")


@register("process")
async def handle_process(message, args: str, ctx) -> None:
    """Handle !process <text> -- advance the plot; asks active players to confirm first."""
    dm_player = ctx.config.get("dm_player", "").strip()
    if dm_player and message.author.display_name != dm_player:
        log.info("!process blocked for %s (only %s may advance)", message.author.display_name, dm_player)
        await message.channel.send(f"Only **{dm_player}** can advance the story with `!process`.")
        return

    player = await resolve_player(message, ctx, require_session=True)
    if player is None:
        return
    log.info("!process from %s (%s): args=%r", player.discord_name, player.character, args[:50] if args else "")

    try:
        async with claim_gate(ctx, "process"):
            candidates = get_active_candidates(ctx, player.user_id)
            if not candidates:
                await _advance_plot(message, args, ctx)
                return

            timeout_sec = ctx.pace.value
            timeout_min = timeout_sec // 60
            mentions = " ".join(f"<@{uid}>" for uid in candidates)
            confirm_text = (
                f"**{message.author.display_name}** wants to advance the plot:\n"
                f"> {args or '(no description)'}\n\n"
                f"{mentions} — react {_CONFIRM} to confirm or {_DENY} to deny. "
                f"Timeout in {timeout_min} minute{'s' if timeout_min != 1 else ''}."
            )

            confirmed = await run_confirmation_gate(
                message, ctx, confirm_text, candidates, timeout_sec,
                require_all=True, action_name="plot advancement",
            )
            if confirmed:
                await _advance_plot(message, args, ctx)
    except GateBusy:
        await message.channel.send("A progress confirmation is already pending.")
