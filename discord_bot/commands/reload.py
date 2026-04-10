"""!reload command -- hot-reload command modules without restarting the bot."""

import importlib
import logging
import sys

from discord_bot.commands import register, COMMANDS

log = logging.getLogger("dm_bot")

# All command modules that can be reloaded
_COMMAND_MODULES = [
    "discord_bot.commands.dm",
    "discord_bot.commands.roll",
    "discord_bot.commands.inventory",
    "discord_bot.commands.status",
    "discord_bot.commands.session",
    "discord_bot.commands.join",
    "discord_bot.commands.help_cmd",
    "discord_bot.commands.overview",
    "discord_bot.commands.save",
    "discord_bot.commands.private",
]


@register("internal-reload")
async def handle_reload(message, args: str, ctx) -> None:
    """Hot-reload command modules. Usage: !reload [module] or !reload (all)."""
    target = args.strip().lower() if args else ""

    if target and target != "all":
        # Reload a single module
        full_name = f"discord_bot.commands.{target}"
        if full_name not in _COMMAND_MODULES:
            await message.channel.send(f"Unknown module: `{target}`")
            return

        if full_name not in sys.modules:
            await message.channel.send(f"Module `{target}` not loaded.")
            return

        try:
            importlib.reload(sys.modules[full_name])
            log.info("Reloaded command module: %s", target)
            await message.channel.send(f"Reloaded `{target}`.")
        except Exception as e:
            log.error("Failed to reload %s: %s", target, e)
            await message.channel.send(f"Failed to reload `{target}`: {e}")
        return

    # Reload all command modules
    reloaded = []
    failed = []
    for mod_name in _COMMAND_MODULES:
        if mod_name not in sys.modules:
            continue
        try:
            importlib.reload(sys.modules[mod_name])
            reloaded.append(mod_name.rsplit(".", 1)[-1])
        except Exception as e:
            log.error("Failed to reload %s: %s", mod_name, e)
            failed.append(f"{mod_name.rsplit('.', 1)[-1]}: {e}")

    parts = [f"Reloaded {len(reloaded)} modules: {', '.join(reloaded)}"]
    if failed:
        parts.append(f"Failed: {'; '.join(failed)}")
    await message.channel.send("\n".join(parts))
