"""Command registry and parser for Discord bot commands."""

from typing import Optional

# Registry of known commands -- handlers are added by each command module
COMMANDS: dict[str, object] = {}


def register(name: str):
    """Decorator to register a command handler function."""
    def decorator(func):
        COMMANDS[name] = func
        return func
    return decorator


def parse_command(content: str) -> Optional[tuple[str, str]]:
    """Parse a Discord message into (command_name, args) or None if not a command."""
    if not content.startswith("!"):
        return None

    parts = content[1:].split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if cmd not in COMMANDS:
        return None

    return cmd, args


# Import command modules to trigger registration
from discord_bot.commands import dm, roll, inventory, status, session, join, help_cmd, overview, save, private  # noqa: E402, F401
