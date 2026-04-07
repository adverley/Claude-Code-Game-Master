"""Manages the Claude Code CLI subprocess and session lifecycle."""

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Optional

log = logging.getLogger("dm_bot.bridge")


class ClaudeBridge:
    def __init__(self, project_dir: str, model: str = "", claude_debug: bool = False):
        self._project_dir = Path(project_dir)
        self._model = model.strip()
        self._claude_debug = claude_debug
        self.session_id: Optional[str] = None
        self._session_started: bool = False
        self._lock = asyncio.Lock()

    @property
    def is_active(self) -> bool:
        return self.session_id is not None

    def start_session(self, campaign: str) -> str:
        """Start a new Claude Code session. Returns the session ID."""
        self.session_id = str(uuid.uuid4())
        self._session_started = False
        model_label = self._model or "Claude Code default"
        log.info("Session created: %s (campaign: %s, model: %s)", self.session_id, campaign, model_label)
        return self.session_id

    def end_session(self) -> None:
        """End the current session."""
        log.info("Session ended: %s", self.session_id)
        self.session_id = None
        self._session_started = False

    def _build_command(self, prompt: str) -> list[str]:
        """Build the claude CLI command list."""
        if not self.is_active:
            raise RuntimeError("No active session. Run !session-start first.")
        if not self._session_started:
            cmd = ["claude", "--print", "--session-id", self.session_id]
        else:
            cmd = ["claude", "--print", "--resume", self.session_id]
        if self._model:
            cmd += ["--model", self._model]
        if self._claude_debug:
            cmd.append("--debug")
        cmd.append(prompt)
        return cmd

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
            action = "init" if not self._session_started else "resume"
            log.info("Claude %s [session=%s, timeout=%.0fs]", action, self.session_id[:8], timeout)
            log.debug("Claude command: %s", " ".join(cmd[:-1]))  # omit prompt from cmd log
            log.debug("--- PROMPT START (%d chars) ---\n%s\n--- PROMPT END ---", len(prompt), prompt)

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._project_dir),
            )
            log.debug("Claude subprocess started (pid=%s)", proc.pid)

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                log.error("Claude timed out after %.0fs (pid=%s)", timeout, proc.pid)
                raise TimeoutError(f"Claude did not respond within {timeout}s")

            stderr_text = stderr.decode().strip() if stderr else ""
            if proc.returncode != 0:
                log.error("Claude exited %d\nstderr: %s", proc.returncode, stderr_text)
                raise RuntimeError(f"Claude exited with code {proc.returncode}: {stderr_text}")

            if stderr_text:
                log.debug("Claude stderr: %s", stderr_text)

            response = stdout.decode().strip()
            log.info("Claude responded (%d chars) [session=%s]", len(response), self.session_id[:8])
            log.debug("--- RESPONSE START ---\n%s\n--- RESPONSE END ---", response)
            self._session_started = True
            return response

    async def send_init(self, campaign: str, players: dict[str, dict], timeout: float = 180.0) -> str:
        """Initialize a new session with the DM prompt."""
        prompt = self._build_init_prompt(campaign, players)
        return await self.send(prompt, timeout=timeout)
