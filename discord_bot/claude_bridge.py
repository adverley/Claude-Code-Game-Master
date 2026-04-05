"""Manages the Claude Code CLI subprocess and session lifecycle."""

import asyncio
import time
from pathlib import Path
from typing import Optional


class ClaudeBridge:
    def __init__(self, project_dir: str):
        self._project_dir = Path(project_dir)
        self.session_id: Optional[str] = None
        self._lock = asyncio.Lock()

    @property
    def is_active(self) -> bool:
        return self.session_id is not None

    def start_session(self, campaign: str) -> str:
        """Start a new Claude Code session. Returns the session ID."""
        timestamp = int(time.time())
        self.session_id = f"discord-{campaign}-{timestamp}"
        return self.session_id

    def end_session(self) -> None:
        """End the current session."""
        self.session_id = None

    def _build_command(self, prompt: str) -> list[str]:
        """Build the claude CLI command list."""
        if not self.is_active:
            raise RuntimeError("No active session. Run !session-start first.")
        return [
            "claude",
            "--print",
            "--session-id", self.session_id,
            prompt,
        ]

    def _build_init_prompt(self, campaign: str, players: dict[str, dict]) -> str:
        """Build the initialization prompt for a new session."""
        player_lines = []
        for uid, info in players.items():
            player_lines.append(f"- {info['discord_name']} plays {info['character']}")
        player_block = "\n".join(player_lines) if player_lines else "- No players registered yet"

        return (
            f"You are the DM for a Discord multi-player D&D session.\n"
            f"Campaign: {campaign}\n\n"
            f"Players:\n{player_block}\n\n"
            f"Each player has their own character file in characters/.\n"
            f"When a player acts, use their character for rolls and state changes.\n"
            f"You can update any character as needed (e.g. area damage hits everyone).\n\n"
            f"Start by running:\n"
            f"  bash tools/dm-session.sh start\n"
            f"  bash tools/dm-session.sh context\n\n"
            f"Then narrate the opening scene based on where the campaign left off.\n"
            f"Respond in character as the DM. Be vivid and engaging."
        )

    async def send(self, prompt: str, timeout: float = 120.0) -> str:
        """Send a prompt to the Claude session and return the response."""
        async with self._lock:
            cmd = self._build_command(prompt)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._project_dir),
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                raise TimeoutError(f"Claude did not respond within {timeout}s")

            if proc.returncode != 0:
                error_msg = stderr.decode().strip() if stderr else "Unknown error"
                raise RuntimeError(f"Claude exited with code {proc.returncode}: {error_msg}")

            return stdout.decode().strip()

    async def send_init(self, campaign: str, players: dict[str, dict], timeout: float = 180.0) -> str:
        """Initialize a new session with the DM prompt."""
        prompt = self._build_init_prompt(campaign, players)
        return await self.send(prompt, timeout=timeout)
