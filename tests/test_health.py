"""Supervisor health monitoring: stalls, crashes, opt-in model escalation."""
import sqlite3
import subprocess
from pathlib import Path

from claudarama.db import init_db, queue_turn
from claudarama.supervisor import Supervisor, load_org_settings


def _script(tmp_path: Path, body: str) -> Path:
    s = tmp_path / "mock_claude"
    s.write_text(f"#!/bin/sh\n{body}\n")
    s.chmod(0o755)
    return s


def _setup(tmp_path: Path, org_yaml: str = "", model: str | None = None):
    db = tmp_path / "office.db"
    init_db(db)
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO people (id, name, role) VALUES ('p1', 'Bender', 'eng')")
    project = tmp_path / "proj"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    subprocess.run(
        ["git", "-C", str(project), "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "-q", "--allow-empty", "-m", "init"],
        check=True,
    )
    pack = project / ".claudarama"
    pack.mkdir()
    (pack / "company.md").write_text("# Co\n")
    (pack / "profiles").mkdir()
    if org_yaml:
        (pack / "org.yaml").write_text(org_yaml)
    out = tmp_path / "out"
    out.mkdir()
    return db, pack, out, queue_turn(db, "p1", model=model)


def _rows(db, sql):
    with sqlite3.connect(db) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute(sql)]


def test_org_settings_defaults_and_overrides(tmp_path):
    (tmp_path / "org.yaml").write_text(
        "# c\nstall_timeout_minutes: 5\nescalate_stuck_turns: true\nescalation_model: opus\n"
    )
    s = load_org_settings(tmp_path)
    assert (s.stall_timeout, s.escalate, s.escalation_model) == (300, True, "opus")
    d = load_org_settings(tmp_path / "missing")
    assert (d.stall_timeout, d.escalate) == (1200, False)


def test_stalled_turn_is_killed_and_fails_by_default(tmp_path):
    db, pack, out, tid = _setup(tmp_path)
    mock = _script(tmp_path, "echo '{}'\nexec sleep 30")
    sup = Supervisor(db, pack, out, claude_binary=str(mock), stall_timeout=0.5)
    sup.run_one_turn(tid)
    assert _rows(db, "SELECT status FROM turns")[0]["status"] == "failed"
    assert len(_rows(db, "SELECT id FROM turns")) == 1  # nothing queued


def test_crash_retried_once_on_same_model(tmp_path):
    db, pack, out, tid = _setup(tmp_path)
    marker = tmp_path / "ran"
    mock = _script(
        tmp_path,
        f'echo "$@" >> {marker}\n[ $(wc -l < {marker}) -ge 2 ] && exit 0\nexit 1',
    )
    Supervisor(db, pack, out, claude_binary=str(mock)).run_one_turn(tid)
    assert _rows(db, "SELECT status FROM turns")[0]["status"] == "done"
    assert len(marker.read_text().splitlines()) == 2


def test_crash_twice_fails(tmp_path):
    db, pack, out, tid = _setup(tmp_path)
    marker = tmp_path / "ran"
    mock = _script(tmp_path, f"echo x >> {marker}\nexit 1")
    Supervisor(db, pack, out, claude_binary=str(mock)).run_one_turn(tid)
    assert _rows(db, "SELECT status FROM turns")[0]["status"] == "failed"
    assert len(marker.read_text().splitlines()) == 2


def test_stall_escalates_to_new_branch_and_queues_higher_model(tmp_path):
    db, pack, out, tid = _setup(
        tmp_path, "escalate_stuck_turns: true\nescalation_model: opus\n"
    )
    mock = _script(tmp_path, "exec sleep 30")
    sup = Supervisor(db, pack, out, claude_binary=str(mock), stall_timeout=0.5)
    sup.run_one_turn(tid)
    rows = _rows(db, "SELECT id, status, model, branch FROM turns")
    assert len(rows) == 2
    old = next(r for r in rows if r["id"] == tid)
    new = next(r for r in rows if r["id"] != tid)
    assert old["status"] == "failed"
    assert (new["status"], new["model"]) == ("queued", "opus")
    branches = subprocess.run(
        ["git", "-C", str(pack.parent), "branch", "--list", new["branch"]],
        capture_output=True, text=True,
    ).stdout
    assert new["branch"] in branches


def test_escalated_turn_that_stalls_does_not_escalate_again(tmp_path):
    db, pack, out, _ = _setup(tmp_path, "escalate_stuck_turns: true\nescalation_model: opus\n")
    tid = queue_turn(db, "p1", model="opus", branch="escalated/x")
    mock = _script(tmp_path, "exec sleep 30")
    Supervisor(db, pack, out, claude_binary=str(mock), stall_timeout=0.5).run_one_turn(tid)
    assert len(_rows(db, "SELECT id FROM turns")) == 2  # original _ + this one, no third


def test_model_flag_passed_to_claude(tmp_path):
    db, pack, out, _ = _setup(tmp_path)
    tid = queue_turn(db, "p1", model="opus")
    marker = tmp_path / "args"
    mock = _script(tmp_path, f'echo "$@" > {marker}')
    Supervisor(db, pack, out, claude_binary=str(mock)).run_one_turn(tid)
    assert "--model opus" in marker.read_text()
