"""Rolling message buffer that tracks Discord channel messages."""

from collections import deque
from datetime import datetime, timezone


class MessageBuffer:
    def __init__(self, max_size: int = 50):
        self._messages: deque[dict] = deque(maxlen=max_size)
        self._sent_index: int = 0  # index into _messages marking last sent position

    def add(self, discord_name: str, character_name: str, content: str, *, is_command: bool) -> None:
        """Add a message to the buffer."""
        self._messages.append({
            "discord_name": discord_name,
            "character_name": character_name,
            "content": content,
            "is_command": is_command,
            "timestamp": datetime.now(timezone.utc).strftime("%H:%M"),
        })

    def get_all(self) -> list[dict]:
        """Return all messages in the buffer."""
        return list(self._messages)

    def get_delta(self) -> list[dict]:
        """Return messages added since the last mark_sent() call."""
        all_msgs = list(self._messages)
        return all_msgs[self._sent_index:]

    def mark_sent(self) -> None:
        """Mark current position -- future get_delta() calls return only newer messages."""
        self._sent_index = len(self._messages)

    def format_for_claude(
        self,
        messages: list[dict],
        *,
        active_player: str,
        active_character: str,
        command_text: str,
    ) -> str:
        """Format a list of messages into the context block sent to Claude."""
        lines = ["[Discord context since last DM response]"]
        for msg in messages:
            lines.append(
                f"[{msg['timestamp']}] {msg['discord_name']} (playing {msg['character_name']}): {msg['content']}"
            )
        lines.append("")
        lines.append(f"Active player: {active_player} ({active_character})")
        lines.append(f"Command: {command_text}")
        return "\n".join(lines)
