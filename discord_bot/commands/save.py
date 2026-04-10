"""!save, !restore, and !list-saves commands -- world-state snapshot management."""

import asyncio
import logging
import shlex

from discord_bot.commands import register

DISCORD_MSG_LIMIT = 2000
log = logging.getLogger("dm_bot.commands")


async def _run_session_cmd(ctx, *args, timeout: float = 30.0):
    """Run a dm-session.sh subcommand and return (returncode, stdout, stderr)."""
    project_dir = str(ctx.claude_bridge._project_dir)
    cmd = "bash tools/dm-session.sh " + " ".join(args)
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=project_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return proc.returncode, stdout.decode().strip(), stderr.decode().strip()


@register("save")
async def handle_save(message, args: str, ctx) -> None:
    """Handle !save <name> -- create a named save point of the current world state."""
    discord_name = message.author.display_name
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id) or "unregistered"
    name = args.strip()

    if not name:
        log.info("!save from %s (%s): empty name", discord_name, character)
        await message.channel.send("Usage: `!save <name>` — e.g. `!save before-boss-fight`")
        return

    if not ctx.claude_bridge.is_active:
        log.info("!save from %s (%s): no active session", discord_name, character)
        await message.channel.send("No active session. Use `!session-start` first.")
        return

    log.info("!save from %s (%s): saving as %r", discord_name, character, name)
    await message.channel.send(f"*Saving world state as **{name}**...*")

    try:
        rc, stdout, stderr = await _run_session_cmd(ctx, "save", shlex.quote(name))
        if rc == 0:
            log.info("!save from %s (%s): saved %r successfully", discord_name, character, name)
            await message.channel.send(f"World state saved as **{name}**.")
        else:
            error = stderr or stdout
            log.error("!save from %s (%s): failed (rc=%d): %s", discord_name, character, rc, error)
            await message.channel.send(f"Save failed: {error}")
    except asyncio.TimeoutError:
        log.warning("!save from %s (%s): timed out for %r", discord_name, character, name)
        await message.channel.send("Save timed out. Try again.")
    except Exception as e:
        log.error("!save from %s (%s): error: %s", discord_name, character, e)
        await message.channel.send(f"Save error: {e}")


@register("restore")
async def handle_restore(message, args: str, ctx) -> None:
    """Handle !restore <save-name> -- restore world state from a save point."""
    discord_name = message.author.display_name
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id) or "unregistered"
    name = args.strip()

    if not name:
        log.info("!restore from %s (%s): empty name", discord_name, character)
        await message.channel.send("Usage: `!restore <save-name>` — e.g. `!restore before-boss-fight`")
        return

    if not ctx.claude_bridge.is_active:
        log.info("!restore from %s (%s): no active session", discord_name, character)
        await message.channel.send("No active session. Use `!session-start` first.")
        return

    log.info("!restore from %s (%s): restoring from %r", discord_name, character, name)
    await message.channel.send(f"*Restoring world state from **{name}**...*")

    try:
        rc, stdout, stderr = await _run_session_cmd(ctx, "restore", shlex.quote(name))
        if rc == 0:
            log.info("!restore from %s (%s): restored %r successfully", discord_name, character, name)
            await message.channel.send(f"World state restored from **{name}**.")
        else:
            error = stderr or stdout
            log.error("!restore from %s (%s): failed (rc=%d): %s", discord_name, character, rc, error)
            await message.channel.send(f"Restore failed: {error}")
    except asyncio.TimeoutError:
        log.warning("!restore from %s (%s): timed out for %r", discord_name, character, name)
        await message.channel.send("Restore timed out. Try again.")
    except Exception as e:
        log.error("!restore from %s (%s): error: %s", discord_name, character, e)
        await message.channel.send(f"Restore error: {e}")


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
            for i in range(0, len(stdout), DISCORD_MSG_LIMIT):
                await message.channel.send(stdout[i:i + DISCORD_MSG_LIMIT])
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
