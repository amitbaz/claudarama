"""Supervisor: picks queued turns, builds briefs, spawns claude -p, captures output."""
import subprocess
from pathlib import Path

from claudarama.brief import build_brief
from claudarama.db import (
    get_queued_turns,
    get_turn,
    mark_turn_done,
    mark_turn_failed,
    mark_turn_running,
    save_brief,
)


class Supervisor:
    """Supervisor loop that executes headless turns.

    For each queued turn it:
    1. Builds a brief from pack files on disk.
    2. Saves the brief to the DB.
    3. Spawns ``claude -p`` (or a mock) with the brief as the prompt.
    4. Streams stdout to a ``.jsonl`` file on disk.
    5. Marks the turn done (exit 0) or failed (non-zero exit).
    """

    def __init__(
        self,
        db_path: Path,
        pack_dir: Path,
        output_dir: Path,
        claude_binary: str = "claude",
    ) -> None:
        self.db_path = db_path
        self.pack_dir = pack_dir
        self.output_dir = output_dir
        self.claude_binary = claude_binary

    def run_one_turn(self, turn_id: str) -> None:
        """Execute a single turn: build brief, spawn process, capture output."""
        turn = get_turn(self.db_path, turn_id)
        if turn is None:
            return

        role = turn["role"]

        # 1. Build the brief from pack files
        brief = build_brief(pack_dir=self.pack_dir, role=role)

        # 2. Save brief to DB
        save_brief(self.db_path, turn_id, brief)

        # 3. Mark as running
        mark_turn_running(self.db_path, turn_id)

        # 4. Spawn the process and capture output
        output_file = self.output_dir / f"{turn_id}.jsonl"
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                result = subprocess.run(
                    [
                        self.claude_binary,
                        "-p", brief,
                        "--output-format", "stream-json",
                    ],
                    stdout=f,
                    stderr=subprocess.PIPE,
                    text=True,
                )

            # 5. Mark done or failed based on exit code
            if result.returncode == 0:
                mark_turn_done(self.db_path, turn_id)
            else:
                mark_turn_failed(self.db_path, turn_id)

        except Exception:
            mark_turn_failed(self.db_path, turn_id)

    def poll(self) -> int:
        """Pick up all queued turns and run them. Returns the count of turns run."""
        queued = get_queued_turns(self.db_path)
        for turn in queued:
            self.run_one_turn(turn["id"])
        return len(queued)
