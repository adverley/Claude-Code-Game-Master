"""Shared command-level primitives: player resolution, thinking-message context, gate claiming."""

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass

log = logging.getLogger("dm_bot.commands.helpers")


@dataclass(frozen=True)
class PlayerInfo:
    user_id: str
    discord_name: str
    character: str  # "unregistered" in lax mode when no character is linked


class GateBusy(RuntimeError):
    """Raised when claim_gate is called for a name that is already pending."""


async def resolve_player(
    message,
    ctx,
    *,
    require_registered: bool = True,
    require_session: bool = False,
) -> PlayerInfo | None:
    """Resolve the message author into a PlayerInfo.

    require_registered=True: posts an error and returns None if no character is linked.
    require_registered=False: returns PlayerInfo with character="unregistered" when unlinked.
    require_session=True: additionally requires an active Claude session, else error+None.
    """
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id)
    discord_name = ctx.player_map.get_discord_name(user_id) or message.author.display_name

    if character is None:
        if require_registered:
            await message.channel.send("You're not registered. Use `!join <character_name>` first.")
            return None
        character = "unregistered"

    if require_session and not ctx.claude_bridge.is_active:
        await message.channel.send("No active session. Use `!session-start` first.")
        return None

    return PlayerInfo(user_id=user_id, discord_name=discord_name, character=character)


@asynccontextmanager
async def with_thinking(channel, text: str = "*The DM is thinking...*"):
    """Post a thinking message; delete it on exit. Delete errors are logged, not raised."""
    thinking_msg = await channel.send(text)
    try:
        yield thinking_msg
    finally:
        try:
            await thinking_msg.delete()
        except Exception as e:
            log.debug("Failed to delete thinking message: %s", e)


@asynccontextmanager
async def claim_gate(ctx, name: str):
    """Reserve ctx.pending_gates[name] for the duration of the block; release on exit.

    Raises GateBusy if the gate is already claimed. Callers should catch and post
    the appropriate "already pending" message themselves.
    """
    if name in ctx.pending_gates:
        raise GateBusy(name)
    ctx.pending_gates.add(name)
    try:
        yield
    finally:
        ctx.pending_gates.discard(name)
