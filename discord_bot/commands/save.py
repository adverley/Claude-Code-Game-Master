"""!save, !restore, and !list-saves commands -- world-state snapshot management."""

import asyncio
import logging
import shlex

from discord_bot.commands import register
from discord_bot.discord_utils import send_chunked

log = logging.getLogger("dm_bot.commands")


async def _run_session_cmd(ctx, *args, timeout: float = 30.0):
    """Run a dm-session.sh subcommand and return (returncode, stdout, stderr)."""
    project_dir = str(ctx.claude_bridge.project_dir)
    cmd = "bash tools/dm-session.sh " + " ".join(args)
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=project_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return proc.returncode, stdout.decode().strip(), stderr.decode().strip()


async def _handle_world_op(message, args: str, ctx, *, action: str, past_tense: str) -> None:
    """Shared implementation for !save and !restore."""
    discord_name = message.author.display_name
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id) or "unregistered"
    name = args.strip()

    if not name:
        log.info("!%s from %s (%s): empty name", action, discord_name, character)
        await message.channel.send(f"Usage: `!{action} <name>` — e.g. `!{action} before-boss-fight`")
        return

    if not ctx.claude_bridge.is_active:
        log.info("!%s from %s (%s): no active session", action, discord_name, character)
        await message.channel.send("No active session. Use `!session-start` first.")
        return

    log.info("!%s from %s (%s): %s as %r", action, discord_name, character, action, name)
    await message.channel.send(f"*{action.capitalize()} world state as **{name}**...*")

    try:
        rc, stdout, stderr = await _run_session_cmd(ctx, action, shlex.quote(name))
        if rc == 0:
            log.info("!%s from %s (%s): %s %r successfully", action, discord_name, character, past_tense, name)
            await message.channel.send(f"World state {past_tense} as **{name}**.")
        else:
            error = stderr or stdout
            log.error("!%s from %s (%s): failed (rc=%d): %s", action, discord_name, character, rc, error)
            await message.channel.send(f"{action.capitalize()} failed: {error}")
    except asyncio.TimeoutError:
        log.warning("!%s from %s (%s): timed out for %r", action, discord_name, character, name)
        await message.channel.send(f"{action.capitalize()} timed out. Try again.")
    except Exception as e:
        log.error("!%s from %s (%s): error: %s", action, discord_name, character, e)
        await message.channel.send(f"{action.capitalize()} error: {e}")


@register("save")
async def handle_save(message, args: str, ctx) -> None:
    """Handle !save <name> -- create a named save point of the current world state."""
    await _handle_world_op(message, args, ctx, action="save", past_tense="saved")


@register("restore")
async def handle_restore(message, args: str, ctx) -> None:
    """Handle !restore <save-name> -- restore world state from a save point."""
    await _handle_world_op(message, args, ctx, action="restore", past_tense="restored")


@register("list-saves")
async def handle_list_saves(message, args: str, ctx) -> None:
    """Handle !list-saves -- show all available save points."""
    discord_name = message.author.display_name
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id) or "unregistered"
    log.info("!list-saves from %s (%s)", discord_name, character)

    try:
        rc, stdout, stderr = await _run_session_cmd(ctx, "list-saves")
        if rc == 0 and stdout:
            await send_chunked(message.channel, stdout)
        elif rc == 0:
            await message.channel.send("No save points found.")
        else:
            error = stderr or stdout
            log.error("!list-saves from %s (%s): failed (rc=%d): %s", discord_name, character, rc, error)
            await message.channel.send(f"Failed to list saves: {error}")
    except asyncio.TimeoutError:
        log.warning("!list-saves from %s (%s): timed out", discord_name, character)
        await message.channel.send("List-saves timed out. Try again.")
    except Exception as e:
        log.error("!list-saves from %s (%s): error: %s", discord_name, character, e)
        await message.channel.send(f"Error: {e}")
