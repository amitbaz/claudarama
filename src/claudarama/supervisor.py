"""Supervisor: picks queued turns, builds briefs, spawns claude -p, captures output."""
import subprocess
from pathlib import Path

from claudarama.brief import build_brief
from claudarama.db import (
    get_queued_turns,
    get_thread,
    get_turn,
    mark_turn_done,
    mark_turn_failed,
    mark_turn_running,
    save_brief,
)


class Supervisor:
    """Supervisor loop that executes headless turns.

    For each queued turn it:
    1. Builds a brief from pack files on disk (plus live thread history if this
       is a reply turn — i.e. ``thread_with`` is set on the turn row).
    2. Saves the brief to the DB.
    3. Spawns ``claude -p`` (or a mock) with the brief as the prompt.
    4. Streams stdout to a ``.jsonl`` file on disk.
    5. Marks the turn done (exit 0) or failed (non-zero exit).

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

        # If this is a reply turn, fetch the live thread from the messages table
        # so the brief contains full conversation history.
        thread = None
        thread_with = turn.get("thread_with")
        if thread_with:
            thread = get_thread(self.db_path, participants=(turn["person_id"], thread_with))

        # 1. Build the brief from pack files (and live thread if this is a reply)
        brief = build_brief(pack_dir=self.pack_dir, role=role, thread=thread)

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
