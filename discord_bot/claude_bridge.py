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
        self._initialized: bool = False
        self._lock = asyncio.Lock()

    @property
    def project_dir(self) -> Path:
        return self._project_dir

    @property
    def is_active(self) -> bool:
        return self.session_id is not None

    def start_session(self, campaign: str) -> str:
        """Start a new Claude Code session. Returns the session ID."""
        self.session_id = str(uuid.uuid4())
        self._initialized = False
        model_label = self._model or "Claude Code default"
        log.info("Session created: %s (campaign: %s, model: %s)", self.session_id, campaign, model_label)
        return self.session_id

    def end_session(self) -> None:
        """End the current session."""
        log.info("Session ended: %s", self.session_id)
        self.session_id = None
        self._initialized = False

    def _build_command(self, prompt: str) -> list[str]:
        """Build the claude CLI command list."""
        if not self.is_active:
            raise RuntimeError("No active session. Run !session-start first.")
        if not self._initialized:
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
            f"This is a multi-player D&D session running via Discord.\n"
            f"Campaign: {campaign}\n\n"
            f"Players:\n{player_block}\n\n"
            f"Only allow a player to perform the action of that character!!!\n"
            f"YOU roll ALL dice for every player — attacks, checks, saves, damage. "
            f"Never ask a player to roll; use `uv run python lib/dice.py \"[notation]\"` yourself.\n\n"
            f"If something happens that only one character would see, hear, or know, "
            f"wrap that part in [PRIVATE:character_name]...[/PRIVATE]. "
            f"It will be sent as a private Discord DM to that player.\n\n"
            f"Use the Read tool to read `.claude/commands/dm.md` and follow the "
            f"CONTINUE CAMPAIGN section.\n"
            f"Skip STEP 0 (campaign selection) — the campaign is `{campaign}`, "
            f"already active.\n"
            f"If the skill routes to `.claude/commands/dm-continue.md`, "
            f"read and follow that instead."
        )

    async def _run_subprocess(self, cmd: list[str], timeout: float, label: str) -> str:
        """Spawn the claude CLI, wait for completion, decode. Raises TimeoutError or RuntimeError."""
        log.debug("Claude %s command: %s", label, " ".join(cmd[:-1]))  # omit prompt from cmd log
        log.debug("--- %s PROMPT START (%d chars) ---\n%s\n--- %s PROMPT END ---",
                 label.upper(), len(cmd[-1]), cmd[-1], label.upper())

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self._project_dir),
        )
        log.debug("Claude subprocess started (pid=%s, label=%s)", proc.pid, label)

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            log.error("Claude %s timed out after %.0fs (pid=%s)", label, timeout, proc.pid)
            raise TimeoutError(f"Claude did not respond within {timeout}s")

        stderr_text = stderr.decode().strip() if stderr else ""
        if proc.returncode != 0:
            log.error("Claude %s exited %d\nstderr: %s", label, proc.returncode, stderr_text)
            raise RuntimeError(f"Claude exited with code {proc.returncode}: {stderr_text}")

        if stderr_text:
            log.debug("Claude %s stderr: %s", label, stderr_text)

        response = stdout.decode().strip()
        log.debug("--- %s RESPONSE START ---\n%s\n--- %s RESPONSE END ---",
                 label.upper(), response, label.upper())
        return response

    async def send(self, prompt: str, timeout: float = 120.0) -> str:
        """Send a prompt to the Claude session and return the response."""
        async with self._lock:
            cmd = self._build_command(prompt)
            label = "init" if not self._initialized else "resume"
            log.info("Claude %s [session=%s, timeout=%.0fs]", label, self.session_id[:8], timeout)
            response = await self._run_subprocess(cmd, timeout, label)
            log.info("Claude responded (%d chars) [session=%s]", len(response), self.session_id[:8])
            self._initialized = True
            return response

    def _build_oneshot_command(self, prompt: str) -> list[str]:
        """Build a one-shot claude CLI command (no session)."""
        cmd = ["claude", "--print"]
        if self._model:
            cmd += ["--model", self._model]
        if self._claude_debug:
            cmd.append("--debug")
        cmd.append(prompt)
        return cmd

    async def send_oneshot(self, prompt: str, timeout: float = 60.0) -> str:
        """Run a single prompt without a session. For lite-mode queries."""
        async with self._lock:
            cmd = self._build_oneshot_command(prompt)
            log.info("Claude oneshot [timeout=%.0fs]", timeout)
            response = await self._run_subprocess(cmd, timeout, "oneshot")
            log.info("Claude oneshot responded (%d chars)", len(response))
            return response

    async def send_init(self, campaign: str, players: dict[str, dict], timeout: float = 180.0) -> str:
        """Initialize a new session with the DM prompt."""
        prompt = self._build_init_prompt(campaign, players)
        return await self.send(prompt, timeout=timeout)
