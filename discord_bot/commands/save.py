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
    name = args.strip()
    if not name:
        await message.channel.send("Usage: `!save <name>` — e.g. `!save before-boss-fight`")
        return

    if not ctx.claude_bridge.is_active:
        await message.channel.send("No active session. Use `!session-start` first.")
        return

    await message.channel.send(f"*Saving world state as **{name}**...*")

    try:
        rc, stdout, stderr = await _run_session_cmd(ctx, "save", shlex.quote(name))
        if rc == 0:
            await message.channel.send(f"World state saved as **{name}**.")
        else:
            error = stderr or stdout
            log.error("Save failed (rc=%d): %s", rc, error)
            await message.channel.send(f"Save failed: {error}")
    except asyncio.TimeoutError:
        log.warning("Save timed out for %s", name)
        await message.channel.send("Save timed out. Try again.")
    except Exception as e:
        log.error("Save error: %s", e)
        await message.channel.send(f"Save error: {e}")


@register("restore")
async def handle_restore(message, args: str, ctx) -> None:
    """Handle !restore <save-name> -- restore world state from a save point."""
    name = args.strip()
    if not name:
        await message.channel.send("Usage: `!restore <save-name>` — e.g. `!restore before-boss-fight`")
        return

    if not ctx.claude_bridge.is_active:
        await message.channel.send("No active session. Use `!session-start` first.")
        return

    await message.channel.send(f"*Restoring world state from **{name}**...*")

    try:
        rc, stdout, stderr = await _run_session_cmd(ctx, "restore", shlex.quote(name))
        if rc == 0:
            await message.channel.send(f"World state restored from **{name}**.")
        else:
            error = stderr or stdout
            log.error("Restore failed (rc=%d): %s", rc, error)
            await message.channel.send(f"Restore failed: {error}")
    except asyncio.TimeoutError:
        log.warning("Restore timed out for %s", name)
        await message.channel.send("Restore timed out. Try again.")
    except Exception as e:
        log.error("Restore error: %s", e)
        await message.channel.send(f"Restore error: {e}")


@register("list-saves")
async def handle_list_saves(message, args: str, ctx) -> None:
    """Handle !list-saves -- show all available save points."""
    try:
        rc, stdout, stderr = await _run_session_cmd(ctx, "list-saves")
        if rc == 0 and stdout:
            for i in range(0, len(stdout), DISCORD_MSG_LIMIT):
                await message.channel.send(stdout[i:i + DISCORD_MSG_LIMIT])
        elif rc == 0:
            await message.channel.send("No save points found.")
        else:
            error = stderr or stdout
            log.error("List-saves failed (rc=%d): %s", rc, error)
            await message.channel.send(f"Failed to list saves: {error}")
    except asyncio.TimeoutError:
        await message.channel.send("List-saves timed out. Try again.")
    except Exception as e:
        log.error("List-saves error: %s", e)
        await message.channel.send(f"Error: {e}")
