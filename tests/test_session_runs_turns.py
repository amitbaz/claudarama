"""The Session's server runs turns (issue #84, ADR-0003).

The office is driven from outside: a scripted ``claude`` stands in for each turn, and the
office server is started the way Claude Code starts it, from the ``--mcp-config`` that
``claudarama open`` hands to ``claude``.
"""
import asyncio
import os
from contextlib import AsyncExitStack
from pathlib import Path

import pytest

from claudarama.db import (
    create_turn_token, get_turn, grant_mandate, init_db, mark_turn_running, queue_turn, register_ticket, resolve_token,
)
from claudarama.scenario.office import project as _project, script as _script, session as _session, until as _until
from claudarama.supervisor import Supervisor, acquire_machine_slot, release_machine_slot


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """The machine-wide slots and pause file live under the home directory; keep the real one out."""
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    return h


# --- a failed launch -----------------------------------------------------------


def test_a_failed_launch_records_its_error_output_on_the_turn(tmp_path):
    db = tmp_path / "office.db"
    init_db(db)
    claude = _script(tmp_path / "claude", "echo 'error: unknown option --frobnicate' >&2\nexit 1")
    turn_id = queue_turn(db, "fullstack-engineer", kind="ritual")

    Supervisor(db, tmp_path / ".claudarama", tmp_path / "out", claude_binary=str(claude)).run_one_turn(turn_id)

    turn = get_turn(db, turn_id)
    assert turn["status"] == "failed"
    assert "unknown option --frobnicate" in turn["error"]


def test_a_launch_that_cannot_start_records_why(tmp_path):
    db = tmp_path / "office.db"
    init_db(db)
    turn_id = queue_turn(db, "fullstack-engineer", kind="ritual")

    Supervisor(db, tmp_path / ".claudarama", tmp_path / "out", claude_binary=str(tmp_path / "no-claude")).run_one_turn(turn_id)

    turn = get_turn(db, turn_id)
    assert turn["status"] == "failed"
    assert "no-claude" in turn["error"]


def test_a_turn_whose_launch_cannot_be_prepared_fails_with_the_reason_instead_of_staying_queued(tmp_path):
    db = tmp_path / "office.db"
    init_db(db)
    (tmp_path / "out").write_text("a file where the transcripts' directory should be")
    turn_id = queue_turn(db, "fullstack-engineer", kind="ritual")

    Supervisor(db, tmp_path / ".claudarama", tmp_path / "out", claude_binary="true").poll()

    turn = get_turn(db, turn_id)
    assert turn["status"] == "failed"
    assert str(tmp_path / "out") in turn["error"]


# --- the open office -------------------------------------------------------------


@pytest.fixture
def bin_dir(tmp_path):
    """Stand-ins first on PATH: a ``gh`` that never reaches GitHub and an ``osascript`` that shows no
    notification. Each test adds its scripted ``claude``."""
    _script(tmp_path / "bin" / "gh", "exit 1")
    _script(tmp_path / "bin" / "osascript", "exit 0")
    return tmp_path / "bin"


def _status(db: Path, turn_id: str) -> str:
    return get_turn(db, turn_id)["status"]


def test_once_the_office_is_open_a_queued_turn_is_launched_and_monitored_to_its_end(tmp_path, bin_dir):
    project, db = _project(tmp_path, "shop")
    _script(bin_dir / "claude", "echo '{\"type\": \"result\"}'")
    turn_id = queue_turn(db, "fullstack-engineer", kind="ritual")

    async def ceo():
        async with _session(project, db, bin_dir):
            await _until(lambda: _status(db, turn_id) == "done", timeout=10)

    asyncio.run(ceo())


def test_at_open_a_turn_left_running_is_queued_again_and_run(tmp_path, bin_dir):
    project, db = _project(tmp_path, "shop")
    _script(bin_dir / "claude", "echo '{\"type\": \"result\"}'")
    turn_id = queue_turn(db, "fullstack-engineer", kind="ritual")
    mark_turn_running(db, turn_id)  # as a Session that closed mid-turn leaves it
    stale_token = create_turn_token(db, turn_id)

    async def ceo():
        async with _session(project, db, bin_dir):
            await _until(lambda: _status(db, turn_id) == "done", timeout=10)

    asyncio.run(ceo())
    mark_turn_running(db, turn_id)
    assert resolve_token(db, stale_token) is None  # the interrupted launch's token did not come back with the turn


def _held_claude(bin_dir: Path, tmp_path: Path) -> tuple[Path, Path]:
    """A scripted ``claude`` that logs each launch (its process id) and runs until the test releases it."""
    launches, release = tmp_path / "launches", tmp_path / "release"
    launches.touch()
    _script(bin_dir / "claude", f"echo $$ >> {launches}\nwhile [ ! -e {release} ]; do sleep 0.1; done")
    return launches, release


def _count(path: Path) -> int:
    return len(path.read_text().splitlines())


def test_a_second_session_leaves_the_running_office_alone_and_runs_it_once_the_first_closes(tmp_path, bin_dir):
    project, db = _project(tmp_path, "shop")
    launches, release = _held_claude(bin_dir, tmp_path)
    turn_id = queue_turn(db, "fullstack-engineer", kind="ritual")

    async def ceo():
        close_first = asyncio.Event()

        async def first_session():
            async with _session(project, db, bin_dir):
                await close_first.wait()

        first = asyncio.create_task(first_session())
        await _until(lambda: _count(launches) == 1)
        async with _session(project, db, bin_dir):  # a second Session on the same project
            await asyncio.sleep(2)  # time enough to take the turn back and launch it again
            assert (_count(launches), _status(db, turn_id)) == (1, "running")
            release.touch()
            await _until(lambda: _status(db, turn_id) == "done")
            assert _count(launches) == 1

            close_first.set()
            await first
            later = queue_turn(db, "fullstack-engineer", kind="ritual")
            await _until(lambda: _status(db, later) == "done")

    asyncio.run(ceo())


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_closing_the_session_stops_a_running_turn_and_the_next_open_runs_it_again(tmp_path, bin_dir):
    project, db = _project(tmp_path, "shop")
    launches, release = _held_claude(bin_dir, tmp_path)
    turn_id = queue_turn(db, "fullstack-engineer", kind="ritual")

    async def open_until(condition):
        async with _session(project, db, bin_dir):
            await _until(condition)

    asyncio.run(open_until(lambda: _count(launches) == 1))  # the Session closes mid-turn

    asyncio.run(_until(lambda: not _alive(int(launches.read_text())), timeout=5))
    release.touch()
    asyncio.run(open_until(lambda: _status(db, turn_id) == "done"))
    assert _count(launches) == 2


def test_a_tickets_turn_interrupted_by_closing_the_session_resumes_in_the_same_worktree(tmp_path, bin_dir):
    project, db = _project(tmp_path, "shop")
    seen, release = tmp_path / "seen", tmp_path / "release"
    seen.touch()
    # Each launch leaves work of its own, and logs where it runs and the work it found there.
    _script(bin_dir / "claude", f"found=$(ls)\ntouch half-done\necho $(pwd) $found >> {seen}\nwhile [ ! -e {release} ]; do sleep 0.1; done")
    grant_mandate(db, "Speed up checkout")
    register_ticket(db, "7", "Speed up checkout")
    turn_id = queue_turn(db, "fullstack-engineer", thread="ticket:7")

    async def open_until(condition):
        async with _session(project, db, bin_dir):
            await _until(condition)

    asyncio.run(open_until(lambda: _count(seen) == 1))  # the Session closes mid-turn
    release.touch()
    asyncio.run(open_until(lambda: _status(db, turn_id) == "done"))

    worktree = tmp_path / "shop-worktrees" / "ticket-7"
    assert seen.read_text().splitlines() == [f"{worktree}", f"{worktree} half-done"]


def test_a_pull_request_merged_outside_the_office_takes_its_tickets_worktree_at_the_next_open(tmp_path, bin_dir):
    project, db = _project(tmp_path, "shop")
    _script(bin_dir / "claude", "echo '{\"type\": \"result\"}'")
    grant_mandate(db, "Speed up checkout")
    register_ticket(db, "7", "Speed up checkout")
    turn_id = queue_turn(db, "fullstack-engineer", thread="ticket:7")
    worktree = tmp_path / "shop-worktrees" / "ticket-7"

    async def open_until(condition):
        async with _session(project, db, bin_dir):
            await _until(condition)

    asyncio.run(open_until(lambda: _status(db, turn_id) == "done"))
    assert worktree.is_dir()

    merged = """case "$*" in "pr list --head ticket-7 "*) echo '[{"state": "MERGED"}]';; *) exit 1;; esac"""
    _script(bin_dir / "gh", merged)  # the CEO merged the ticket's pull request on GitHub
    asyncio.run(open_until(lambda: not worktree.exists()))


# --- how many turns run at once ---------------------------------------------------


def _gathering_claude(bin_dir: Path, tmp_path: Path, patience: float) -> Path:
    """A scripted ``claude`` that waits up to *patience* seconds for a second turn to be running
    beside it, then logs how many are. Returns the log, one count per turn."""
    seen = tmp_path / "seen"
    seen.mkdir()
    _script(bin_dir / "claude", f"""
touch {seen}/running.$$
n=0
while [ $(ls {seen} | grep -c running) -lt 2 ] && [ $n -lt {int(patience * 10)} ]; do sleep 0.1; n=$((n+1)); done
ls {seen} | grep -c running >> {seen}/counts
sleep 0.5
rm {seen}/running.$$
""")
    return seen / "counts"


def _run_offices(bin_dir: Path, offices: list[tuple[Path, Path]], turns: list[tuple[Path, str]]) -> None:
    """Open a Session on each office and keep them open until every turn is done."""

    async def ceo():
        async with AsyncExitStack() as sessions:
            for project, db in offices:
                await sessions.enter_async_context(_session(project, db, bin_dir))
            await _until(lambda: all(_status(db, turn_id) == "done" for db, turn_id in turns))

    asyncio.run(ceo())


def _counts(log: Path) -> list[int]:
    return [int(line) for line in log.read_text().split()]


def test_a_role_runs_one_turn_at_a_time(tmp_path, bin_dir):
    office = _project(tmp_path, "shop")
    counts = _gathering_claude(bin_dir, tmp_path, patience=1)
    turns = [(office[1], queue_turn(office[1], "fullstack-engineer", kind="ritual")) for _ in range(2)]

    _run_offices(bin_dir, [office], turns)

    assert _counts(counts) == [1, 1]


@pytest.mark.parametrize("org_yaml, at_once", [("", [2, 2]), ("concurrency: 1\n", [1, 1])])
def test_an_office_runs_turns_at_the_same_time_up_to_its_cap(tmp_path, bin_dir, org_yaml, at_once):
    office = _project(tmp_path, "shop", org_yaml)
    counts = _gathering_claude(bin_dir, tmp_path, patience=1 if at_once == [1, 1] else 10)
    turns = [(office[1], queue_turn(office[1], role, kind="ritual")) for role in ("fullstack-engineer", "designer")]

    _run_offices(bin_dir, [office], turns)

    assert _counts(counts) == at_once


def test_two_offices_on_one_machine_run_turns_at_the_same_time(tmp_path, bin_dir):
    offices = [_project(tmp_path, name) for name in ("shop", "blog")]
    counts = _gathering_claude(bin_dir, tmp_path, patience=10)
    turns = [(db, queue_turn(db, "fullstack-engineer", kind="ritual")) for _, db in offices]

    _run_offices(bin_dir, offices, turns)

    assert _counts(counts) == [2, 2]


def test_two_offices_share_the_machine_wide_cap(tmp_path, bin_dir):
    offices = [_project(tmp_path, name) for name in ("shop", "blog")]
    counts = _gathering_claude(bin_dir, tmp_path, patience=1)
    turns = [(db, queue_turn(db, "fullstack-engineer", kind="ritual")) for _, db in offices]
    taken = [acquire_machine_slot() for _ in range(9)]  # other offices hold all but one of the machine's ten

    try:
        _run_offices(bin_dir, offices, turns)
    finally:
        for slot in taken:
            release_machine_slot(slot)

    assert _counts(counts) == [1, 1]
