"""Supervisor: picks queued turns, builds briefs, spawns claude -p, captures output.

Health: a crash (non-zero exit) is retried once on the same model. A stalled turn
(no stdout for ``stall_timeout`` seconds) is killed; it fails unless ``org.yaml``
opts in to escalation, in which case a retry is queued on a higher model on a new branch.
"""
import json
import os
import selectors
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from claudarama.brief import build_brief
from claudarama.gate import OFFICE_ENV, build_allowlist
from claudarama.session import mcp_config
from claudarama.db import (
    create_turn_token,
    get_queued_turns,
    get_thread,
    get_turn,
    grant_refusal,
    mark_turn_done,
    mark_turn_failed,
    mark_turn_running,
    queue_turn,
    refuse_turn,
    save_brief,
)


@dataclass
class TurnLaunch:
    """Everything a turn is started with. Built by ``Supervisor.build_launch``."""

    brief: str
    cmd: list[str]
    env: dict[str, str] | None = None  # None = inherit the supervisor's environment


@dataclass
class OrgSettings:
    stall_timeout: float = 20 * 60
    escalate: bool = False
    escalation_model: str = "opus"


def load_org_settings(pack_dir: Path) -> OrgSettings:
    """Read the health keys from ``org.yaml`` (flat ``key: value`` lines only)."""
    settings = OrgSettings()
    try:
        text = (pack_dir / "org.yaml").read_text(encoding="utf-8")
    except OSError:
        return settings
    for line in text.splitlines():
        key, sep, value = line.split("#", 1)[0].partition(":")
        key, value = key.strip(), value.strip()
        if not sep:
            continue
        if key == "stall_timeout_minutes":
            try:
                settings.stall_timeout = float(value) * 60
            except ValueError:
                pass  # keep default on a malformed value
        elif key == "escalate_stuck_turns":
            settings.escalate = value.lower() == "true"
        elif key == "escalation_model" and value:
            settings.escalation_model = value
    return settings


class Supervisor:
    """Supervisor loop that executes headless turns.

    For each queued turn it builds a brief from pack files on disk (plus live
    thread history if this is a reply turn, i.e. ``thread`` is set), saves
    it, spawns ``claude -p`` and streams stdout to a ``.jsonl`` file.

    Sending a message mid-turn is handled by the daemon's ``send`` MCP tool,
    which marks the turn done and queues the receiver's turn directly.  The
    supervisor does not manage that lifecycle; it only drives turns that are
    in the ``queued`` state.
    """

    def __init__(
        self,
        db_path: Path,
        pack_dir: Path,
        output_dir: Path,
        claude_binary: str = "claude",
        stall_timeout: float | None = None,
        host: str = "127.0.0.1",
        port: int = 8000,
    ) -> None:
        self.db_path = db_path
        self.pack_dir = pack_dir
        self.output_dir = output_dir
        self.claude_binary = claude_binary
        self.stall_timeout_override = stall_timeout
        self.host = host
        self.port = port

    def _spawn(
        self, launch: TurnLaunch, output_file: Path, stall_timeout: float, mode: str = "w"
    ) -> str:
        """Run the launch command, streaming stdout to output_file. Returns 'ok', 'crash' or 'stalled'."""
        with open(output_file, mode, encoding="utf-8") as f:
            proc = subprocess.Popen(
                launch.cmd,
                env=launch.env,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            sel = selectors.DefaultSelector()
            sel.register(proc.stdout, selectors.EVENT_READ)
            last_output = time.monotonic()
            try:
                while True:
                    remaining = stall_timeout - (time.monotonic() - last_output)
                    if remaining <= 0:
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass  # exited just now; still counts as stalled
                        proc.wait()
                        return "stalled"
                    if not sel.select(timeout=remaining):
                        continue
                    chunk = os.read(proc.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    f.write(chunk.decode("utf-8", errors="replace"))
                    f.flush()
                    last_output = time.monotonic()
                return "ok" if proc.wait() == 0 else "crash"
            finally:
                sel.close()
                proc.stdout.close()

    def _create_branch(self, name: str) -> bool:
        res = subprocess.run(
            ["git", "-C", str(self.pack_dir.parent), "branch", name],
            capture_output=True,
        )
        return res.returncode == 0

    def build_launch(self, turn: dict) -> TurnLaunch:
        """Assemble the brief, ``claude`` command and environment for a turn. Spawns nothing."""
        # A reply turn gets the live thread from the messages table.
        thread = None
        if turn.get("thread"):
            thread = get_thread(self.db_path, turn["thread"])

        brief = build_brief(pack_dir=self.pack_dir, role=turn["role"], thread=thread)
        if turn["branch"]:
            brief += f"\n\nWork on git branch `{turn['branch']}`.\n"

        token = create_turn_token(self.db_path, turn["id"])
        cmd = [
            self.claude_binary, "-p", brief, "--output-format", "stream-json",
            "--mcp-config", mcp_config(self.host, self.port, token),
        ]
        if turn["model"]:
            cmd += ["--model", turn["model"]]

        # One allowlist feeds both walls: native rules (unlisted calls denied) and the gate hook.
        allow, deny = build_allowlist(self.pack_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        settings_path = self.output_dir / f"{turn['id']}.settings.json"
        settings_path.write_text(json.dumps({
            "permissions": {"allow": allow, "deny": deny},
            "hooks": {"PreToolUse": [{"matcher": "", "hooks": [
                {"type": "command", "command": f"{shlex.quote(sys.executable)} -m claudarama.gate"}
            ]}]},
        }), encoding="utf-8")
        cmd += ["--settings", str(settings_path), "--permission-mode", "dontAsk"]
        return TurnLaunch(brief=brief, cmd=cmd, env={**os.environ, OFFICE_ENV: str(settings_path)})

    def run_one_turn(self, turn_id: str) -> None:
        """Execute a single turn: build brief, spawn process, handle crash/stall."""
        turn = get_turn(self.db_path, turn_id)
        if turn is None:
            return

        reason = grant_refusal(self.db_path, turn)
        if reason:
            refuse_turn(self.db_path, turn_id, reason)
            return

        settings = load_org_settings(self.pack_dir)
        stall_timeout = (
            self.stall_timeout_override
            if self.stall_timeout_override is not None
            else settings.stall_timeout
        )

        launch = self.build_launch(turn)
        save_brief(self.db_path, turn_id, launch.brief)
        mark_turn_running(self.db_path, turn_id)
        output_file = self.output_dir / f"{turn_id}.jsonl"

        try:
            outcome = self._spawn(launch, output_file, stall_timeout)
            if outcome == "crash":  # one retry, same model
                outcome = self._spawn(launch, output_file, stall_timeout, mode="a")
        except Exception:
            outcome = "crash"

        if outcome == "ok":
            mark_turn_done(self.db_path, turn_id)
            return

        mark_turn_failed(self.db_path, turn_id)
        # ponytail: escalates once; an already-escalated turn just fails (no pause or notify yet).
        if (
            outcome == "stalled"
            and settings.escalate
            and turn["model"] != settings.escalation_model
        ):
            branch = f"escalated/{turn_id[:8]}"
            if self._create_branch(branch):
                queue_turn(
                    self.db_path,
                    turn["person_id"],
                    thread=turn["thread"],
                    model=settings.escalation_model,
                    branch=branch,
                )

    def poll(self) -> int:
        """Pick up all queued turns and run them. Returns the count of turns run."""
        queued = get_queued_turns(self.db_path)
        for turn in queued:
            self.run_one_turn(turn["id"])
        return len(queued)
