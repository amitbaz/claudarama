"""Supervisor: picks queued turns, builds briefs, spawns claude -p, captures output.

Health: a crash (non-zero exit) is retried once on the same model. A stalled turn
(no stdout for ``stall_timeout`` seconds) is killed; it fails unless ``org.yaml``
opts in to escalation, in which case a retry is queued on a higher model on a new branch.
"""
import os
import selectors
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from claudarama.brief import build_brief
from claudarama.db import (
    get_queued_turns,
    get_turn,
    mark_turn_done,
    mark_turn_failed,
    mark_turn_running,
    queue_turn,
    save_brief,
)


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
            settings.stall_timeout = float(value) * 60
        elif key == "escalate_stuck_turns":
            settings.escalate = value.lower() == "true"
        elif key == "escalation_model" and value:
            settings.escalation_model = value
    return settings


class Supervisor:
    """Supervisor loop that executes headless turns."""

    def __init__(
        self,
        db_path: Path,
        pack_dir: Path,
        output_dir: Path,
        claude_binary: str = "claude",
        stall_timeout: float | None = None,
    ) -> None:
        self.db_path = db_path
        self.pack_dir = pack_dir
        self.output_dir = output_dir
        self.claude_binary = claude_binary
        self.stall_timeout_override = stall_timeout

    def _spawn(self, cmd: list[str], output_file: Path, stall_timeout: float) -> str:
        """Run cmd, streaming stdout to output_file. Returns 'ok', 'crash' or 'stalled'."""
        with open(output_file, "w", encoding="utf-8") as f:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True
            )
            sel = selectors.DefaultSelector()
            sel.register(proc.stdout, selectors.EVENT_READ)
            last_output = time.monotonic()
            try:
                while True:
                    remaining = stall_timeout - (time.monotonic() - last_output)
                    if remaining <= 0:
                        os.killpg(proc.pid, signal.SIGKILL)
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

    def run_one_turn(self, turn_id: str) -> None:
        """Execute a single turn: build brief, spawn process, handle crash/stall."""
        turn = get_turn(self.db_path, turn_id)
        if turn is None:
            return

        settings = load_org_settings(self.pack_dir)
        stall_timeout = self.stall_timeout_override or settings.stall_timeout

        brief = build_brief(pack_dir=self.pack_dir, role=turn["role"])
        if turn["branch"]:
            brief += f"\n\nWork on git branch `{turn['branch']}`.\n"
        save_brief(self.db_path, turn_id, brief)
        mark_turn_running(self.db_path, turn_id)

        cmd = [self.claude_binary, "-p", brief, "--output-format", "stream-json"]
        if turn["model"]:
            cmd += ["--model", turn["model"]]
        output_file = self.output_dir / f"{turn_id}.jsonl"

        try:
            outcome = self._spawn(cmd, output_file, stall_timeout)
            if outcome == "crash":  # one retry, same model
                outcome = self._spawn(cmd, output_file, stall_timeout)
        except Exception:
            outcome = "crash"

        if outcome == "ok":
            mark_turn_done(self.db_path, turn_id)
            return

        mark_turn_failed(self.db_path, turn_id)
        # ponytail: escalates once; an already-escalated turn just fails (paused for the CEO).
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
                    model=settings.escalation_model,
                    branch=branch,
                )

    def poll(self) -> int:
        """Pick up all queued turns and run them. Returns the count of turns run."""
        queued = get_queued_turns(self.db_path)
        for turn in queued:
            self.run_one_turn(turn["id"])
        return len(queued)
