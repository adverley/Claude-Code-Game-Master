"""!summary command -- generate a brief story recap for the party."""

import logging
from discord_bot.commands import register
from discord_bot.response_router import route_response
from discord_bot.commands.dm import _dispatch_whispers

DISCORD_MSG_LIMIT = 2000
log = logging.getLogger("dm_bot.commands")


@register("summary")
async def handle_summary(message, args: str, ctx) -> None:
    """Handle !summary -- ask Claude for a 1-3 sentence story recap."""
    if not ctx.claude_bridge.is_active:
        await message.channel.send("No active session. Use `!session-start` to begin a game.")
        return

    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id)

    prompt = (
        "Summarize the story so far in 1 to 3 sentences for all players. "
        "Be narrative and evocative — capture the key events and current situation. "
        "Do not advance the plot."
    )
    if character:
        prompt += (
            f" Then add one sentence specifically relevant to {character}'s "
            f"journey, perspective, or current circumstances."
        )

    thinking_msg = await message.channel.send("*The DM is recalling the tale...*")
    try:
        response = await ctx.claude_bridge.send(prompt)
        routed = route_response(response)

        if routed.public:
            for i in range(0, len(routed.public), DISCORD_MSG_LIMIT):
                await message.channel.send(routed.public[i:i + DISCORD_MSG_LIMIT])

        await _dispatch_whispers(routed.whispers, ctx.player_map, ctx.client, message.channel)
    except TimeoutError:
        log.warning("Claude timed out for !summary from %s", message.author.display_name)
        await message.channel.send("The DM took too long to respond. Try again.")
    except RuntimeError as e:
        log.error("Claude error for !summary: %s", e)
        await message.channel.send(f"DM error: {e}")
    finally:
        await thinking_msg.delete()
