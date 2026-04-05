"""Discord bot entry point -- connects to Discord, tracks messages, dispatches commands."""

import asyncio
import sys
from pathlib import Path
from dataclasses import dataclass

import discord

from discord_bot.config import load_config
from discord_bot.message_buffer import MessageBuffer
from discord_bot.claude_bridge import ClaudeBridge
from discord_bot.player_map import PlayerMap
from discord_bot.commands import parse_command, COMMANDS

PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


@dataclass
class BotContext:
    """Shared state passed to all command handlers."""
    config: dict
    message_buffer: MessageBuffer
    claude_bridge: ClaudeBridge
    player_map: PlayerMap
    channel_id: int


def on_message_handler(message, ctx: BotContext) -> str:
    """
    Synchronous message pre-processing. Returns:
    - "ignored" if the message should be skipped
    - "tracked" if it was a non-command message (added to buffer)
    - "command" if it's a command that needs async dispatch
    """
    # Ignore bot messages
    if message.author.bot:
        return "ignored"

    # Ignore messages from other channels
    if message.channel.id != ctx.channel_id:
        return "ignored"

    # Look up player info for buffer tracking
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id) or "unregistered"
    discord_name = ctx.player_map.get_discord_name(user_id) or message.author.display_name

    # Track all messages in buffer
    parsed = parse_command(message.content)
    ctx.message_buffer.add(
        discord_name=discord_name,
        character_name=character,
        content=message.content,
        is_command=parsed is not None,
    )

    if parsed is not None:
        return "command"

    return "tracked"


async def dispatch_command(message, ctx: BotContext) -> None:
    """Parse and dispatch a command message."""
    parsed = parse_command(message.content)
    if parsed is None:
        return

    cmd_name, args = parsed
    handler = COMMANDS.get(cmd_name)
    if handler:
        await handler(message, args, ctx)


def main():
    """Run the Discord bot."""
    config = load_config(CONFIG_PATH)

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    campaign_dir = PROJECT_DIR / "world-state" / "campaigns" / config["campaign"]
    player_map_path = campaign_dir / "player-map.json"

    ctx = BotContext(
        config=config,
        message_buffer=MessageBuffer(max_size=config["message_buffer_size"]),
        claude_bridge=ClaudeBridge(project_dir=str(PROJECT_DIR)),
        player_map=PlayerMap(player_map_path),
        channel_id=int(config["channel_id"]),
    )

    @client.event
    async def on_ready():
        print(f"Bot connected as {client.user}")
        print(f"Listening in channel: {ctx.channel_id}")
        print(f"Campaign: {config['campaign']}")

    @client.event
    async def on_message(message):
        result = on_message_handler(message, ctx)
        if result == "command":
            await dispatch_command(message, ctx)

    client.run(config["bot_token"])


if __name__ == "__main__":
    main()
