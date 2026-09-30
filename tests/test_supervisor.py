"""Tests for the Supervisor seam: headless turn execution with briefs.

The Supervisor Seam (per spec #21): a mock executable replaces `claude -p`.
We enqueue a turn, run the supervisor, and assert it spawns the mock, captures
output to disk, updates DB status, and builds a brief.
"""
import json
import sqlite3
import textwrap
from pathlib import Path

import pytest

from claudarama.db import init_db


# ---------------------------------------------------------------------------
# Slice 1: DB turn lifecycle (queue → pick → done)
# ---------------------------------------------------------------------------


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _seed_person(db_path: Path, person_id: str = "p1", name: str = "Bender", role: str = "fullstack-engineer") -> str:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO people (id, name, role) VALUES (?, ?, ?)",
            (person_id, name, role),
        )
    return person_id


class TestTurnLifecycle:
    """Turn lifecycle through the DB public functions."""

    def test_queue_turn_creates_queued_row(self, tmp_path):
        from claudarama.db import queue_turn

        db_path = tmp_path / "office.db"
        init_db(db_path)
        _seed_person(db_path, "p1")

        turn_id = queue_turn(db_path, person_id="p1")
        assert turn_id  # non-empty string

        with _connect(db_path) as conn:
            row = conn.execute("SELECT status FROM turns WHERE id = ?", (turn_id,)).fetchone()
        assert row["status"] == "queued"

    def test_get_queued_turns_returns_only_queued(self, tmp_path):
        from claudarama.db import get_queued_turns, queue_turn

        db_path = tmp_path / "office.db"
        init_db(db_path)
        _seed_person(db_path, "p1")
        _seed_person(db_path, "p2", name="Leela", role="cpo")

        queue_turn(db_path, person_id="p1")
        queue_turn(db_path, person_id="p2")

        # Manually mark one as running to verify it's excluded
        with sqlite3.connect(db_path) as conn:
            first = conn.execute("SELECT id FROM turns WHERE person_id = 'p1'").fetchone()[0]
            conn.execute("UPDATE turns SET status = 'running' WHERE id = ?", (first,))

        queued = get_queued_turns(db_path)
        assert len(queued) == 1
        assert queued[0]["person_id"] == "p2"

    def test_mark_turn_done_updates_status_and_ended_at(self, tmp_path):
        from claudarama.db import mark_turn_done, queue_turn

        db_path = tmp_path / "office.db"
        init_db(db_path)
        _seed_person(db_path, "p1")

        turn_id = queue_turn(db_path, person_id="p1")
        mark_turn_done(db_path, turn_id)

        with _connect(db_path) as conn:
            row = conn.execute("SELECT status, ended_at FROM turns WHERE id = ?", (turn_id,)).fetchone()
        assert row["status"] == "done"
        assert row["ended_at"] is not None

    def test_mark_turn_failed_updates_status(self, tmp_path):
        from claudarama.db import mark_turn_failed, queue_turn

        db_path = tmp_path / "office.db"
        init_db(db_path)
        _seed_person(db_path, "p1")

        turn_id = queue_turn(db_path, person_id="p1")
        mark_turn_failed(db_path, turn_id)

        with _connect(db_path) as conn:
            row = conn.execute("SELECT status, ended_at FROM turns WHERE id = ?", (turn_id,)).fetchone()
        assert row["status"] == "failed"
        assert row["ended_at"] is not None


# ---------------------------------------------------------------------------
# Slice 2: Brief builder reads company.md + role file from pack on disk
# ---------------------------------------------------------------------------


class TestBriefBuilder:
    """Brief assembly from pack files on disk."""

    def _make_pack(self, tmp_path: Path) -> Path:
        pack = tmp_path / ".claudarama"
        pack.mkdir()
        (pack / "company.md").write_text("# Acme Corp\nGoal: ship v1\n")
        profiles = pack / "profiles"
        profiles.mkdir()
        (profiles / "fullstack-engineer.md").write_text("You are a fullstack engineer.\n")
        return pack

    def test_build_brief_includes_company_and_role(self, tmp_path):
        from claudarama.brief import build_brief

        pack = self._make_pack(tmp_path)
        brief = build_brief(pack_dir=pack, role="fullstack-engineer")

        assert "Acme Corp" in brief
        assert "fullstack engineer" in brief

    def test_build_brief_missing_role_file_still_includes_company(self, tmp_path):
        from claudarama.brief import build_brief

        pack = tmp_path / ".claudarama"
        pack.mkdir()
        (pack / "company.md").write_text("# Acme Corp\n")
        (pack / "profiles").mkdir()

        brief = build_brief(pack_dir=pack, role="nonexistent-role")
        assert "Acme Corp" in brief
        # No crash, just no role section

    def test_build_brief_missing_company_md(self, tmp_path):
        from claudarama.brief import build_brief

        pack = tmp_path / ".claudarama"
        pack.mkdir()
        (pack / "profiles").mkdir()

        brief = build_brief(pack_dir=pack, role="fullstack-engineer")
        # Should not crash; returns whatever it can
        assert isinstance(brief, str)


# ---------------------------------------------------------------------------
# Slice 3: Supervisor spawns mock executable, captures output, marks done
# ---------------------------------------------------------------------------


def _make_mock_claude(tmp_path: Path, output_lines: list[str] | None = None) -> Path:
    """Create a small script that prints JSON lines to stdout and exits 0."""
    if output_lines is None:
        output_lines = [
            json.dumps({"type": "assistant", "message": "Hello from mock claude"}),
        ]
    script = tmp_path / "mock_claude"
    body = "\n".join(f'echo \'{line}\'' for line in output_lines)
    script.write_text(f"#!/bin/sh\n{body}\n")
    script.chmod(0o755)
    return script


def _make_failing_claude(tmp_path: Path) -> Path:
    """Create a mock executable that exits with code 1."""
    script = tmp_path / "mock_claude"
    script.write_text("#!/bin/sh\necho '{\"error\": true}'\nexit 1\n")
    script.chmod(0o755)
    return script


class TestSupervisor:
    """Supervisor seam: enqueue → run → assert DB + disk."""

    def _setup(self, tmp_path: Path, mock_script: Path | None = None):
        from claudarama.db import queue_turn

        db_path = tmp_path / "office.db"
        init_db(db_path)
        _seed_person(db_path, "p1", role="fullstack-engineer")

        pack = tmp_path / ".claudarama"
        pack.mkdir()
        (pack / "company.md").write_text("# Test Co\nGoal: test\n")
        profiles = pack / "profiles"
        profiles.mkdir()
        (profiles / "fullstack-engineer.md").write_text("You are a fullstack engineer.\n")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        if mock_script is None:
            mock_script = _make_mock_claude(tmp_path)

        turn_id = queue_turn(db_path, person_id="p1", kind="ritual")

        return db_path, pack, output_dir, mock_script, turn_id

    def test_run_one_turn_spawns_mock_and_marks_done(self, tmp_path):
        from claudarama.supervisor import Supervisor

        db_path, pack, output_dir, mock_script, turn_id = self._setup(tmp_path)

        sup = Supervisor(
            db_path=db_path,
            pack_dir=pack,
            output_dir=output_dir,
            claude_binary=str(mock_script),
        )
        sup.run_one_turn(turn_id)

        # Turn is marked done
        with _connect(db_path) as conn:
            row = conn.execute("SELECT status FROM turns WHERE id = ?", (turn_id,)).fetchone()
        assert row["status"] == "done"

    def test_run_one_turn_captures_output_to_jsonl(self, tmp_path):
        from claudarama.supervisor import Supervisor

        expected_line = json.dumps({"type": "assistant", "message": "Hello"})
        mock_script = _make_mock_claude(tmp_path, [expected_line])
        db_path, pack, output_dir, _, turn_id = self._setup(tmp_path, mock_script)

        sup = Supervisor(
            db_path=db_path,
            pack_dir=pack,
            output_dir=output_dir,
            claude_binary=str(mock_script),
        )
        sup.run_one_turn(turn_id)

        # Output file exists and contains the expected line
        jsonl_file = output_dir / f"{turn_id}.jsonl"
        assert jsonl_file.exists()
        lines = jsonl_file.read_text().strip().splitlines()
        assert len(lines) >= 1
        parsed = json.loads(lines[0])
        assert parsed["type"] == "assistant"

    def test_run_one_turn_saves_brief_to_db(self, tmp_path):
        from claudarama.supervisor import Supervisor

        db_path, pack, output_dir, mock_script, turn_id = self._setup(tmp_path)

        sup = Supervisor(
            db_path=db_path,
            pack_dir=pack,
            output_dir=output_dir,
            claude_binary=str(mock_script),
        )
        sup.run_one_turn(turn_id)

        # Brief was saved to DB
        with _connect(db_path) as conn:
            row = conn.execute("SELECT content FROM briefs WHERE turn_id = ?", (turn_id,)).fetchone()
        assert row is not None
        assert "Test Co" in row["content"]

    def test_run_one_turn_failed_exit_marks_failed(self, tmp_path):
        from claudarama.supervisor import Supervisor

        mock_script = _make_failing_claude(tmp_path)
        db_path, pack, output_dir, _, turn_id = self._setup(tmp_path, mock_script)

        sup = Supervisor(
            db_path=db_path,
            pack_dir=pack,
            output_dir=output_dir,
            claude_binary=str(mock_script),
        )
        sup.run_one_turn(turn_id)

        with _connect(db_path) as conn:
            row = conn.execute("SELECT status FROM turns WHERE id = ?", (turn_id,)).fetchone()
        assert row["status"] == "failed"

    def test_poll_picks_up_queued_turn_and_runs_it(self, tmp_path):
        from claudarama.supervisor import Supervisor

        db_path, pack, output_dir, mock_script, turn_id = self._setup(tmp_path)

        sup = Supervisor(
            db_path=db_path,
            pack_dir=pack,
            output_dir=output_dir,
            claude_binary=str(mock_script),
        )
        turns_run = sup.poll()
        assert turns_run == 1

        with _connect(db_path) as conn:
            row = conn.execute("SELECT status FROM turns WHERE id = ?", (turn_id,)).fetchone()
        assert row["status"] == "done"

    def test_poll_returns_zero_when_nothing_queued(self, tmp_path):
        from claudarama.supervisor import Supervisor

        db_path = tmp_path / "office.db"
        init_db(db_path)

        pack = tmp_path / ".claudarama"
        pack.mkdir()
        (pack / "company.md").write_text("# Empty\n")
        (pack / "profiles").mkdir()

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        sup = Supervisor(
            db_path=db_path,
            pack_dir=pack,
            output_dir=output_dir,
            claude_binary="echo",
        )
        turns_run = sup.poll()
        assert turns_run == 0


class TestBuildLaunch:
    """Launch seam: everything a turn starts with, inspectable without spawning."""

    def test_build_launch_assembles_brief_command_and_env(self, tmp_path):
        from claudarama.db import get_turn, queue_turn
        from claudarama.supervisor import Supervisor

        db_path = tmp_path / "office.db"
        init_db(db_path)
        _seed_person(db_path, "p1", role="fullstack-engineer")
        pack = tmp_path / ".claudarama"
        (pack / "profiles").mkdir(parents=True)
        (pack / "company.md").write_text("# Test Co\n")
        output_dir = tmp_path / "output"
        turn_id = queue_turn(db_path, person_id="p1", model="opus", branch="feat/x")
        sup = Supervisor(db_path, pack, output_dir, claude_binary="claude")

        launch = sup.build_launch(get_turn(db_path, turn_id))

        assert "Test Co" in launch.brief
        assert "feat/x" in launch.brief
        assert launch.cmd[:5] == ["claude", "-p", launch.brief, "--output-format", "stream-json"]
        assert launch.cmd[7:] == ["--model", "opus"]
        assert launch.cmd[5] == "--mcp-config"
        assert launch.env is None  # inherit; later gates tickets fill this in
