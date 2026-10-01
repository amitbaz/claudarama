"""Reaching the CEO (issue #94): messages addressed to the CEO, and the watcher that wakes the Assistant.

Notifications and the gates answered inside the Session are asserted in the loop scenario
(``scenarios/loop.json``).
"""
import asyncio
import threading
from unittest.mock import patch

import pytest

from claudarama.cli import main
from claudarama.daemon import create_mcp_server
from claudarama.db import (
    create_turn_token, get_office_db_path, get_owner_token, get_queued_turns, get_turn, grant_mandate, init_db,
    mark_turn_running, queue_turn, record_challenge, resolve_diagnosis_gate, submit_diagnosis,
)
from claudarama.session import open_ceo_session


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "office.db"
    init_db(path)
    return path


def _send_to_the_ceo(db, role: str, msg_type: str, body: str, **thread) -> tuple[dict, str]:
    """A turn of *role* sends the CEO a message. Returns the tool's answer and the turn."""
    turn = queue_turn(db, role, kind="ritual")
    mark_turn_running(db, turn)
    send = create_mcp_server(db_path=db, token=create_turn_token(db, turn))._tool_manager.get_tool("send").fn
    return asyncio.run(send(receiver_id="ceo", msg_type=msg_type, body=body, **thread)), turn


def _open(db, tmp_path) -> str:
    """The CEO opens the office from the terminal. Returns what the Assistant is given."""
    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        assert open_ceo_session(db_path=db, pack_dir=tmp_path) == 0
    launch = run.call_args.args[0]
    return launch[launch.index("--append-system-prompt") + 1]


def test_a_message_to_the_ceo_is_accepted_and_ends_the_turn_without_waking_anyone(db):
    answer, turn = _send_to_the_ceo(db, "pm", "BLOCKED", "I need the staging key.", ticket="2")

    assert answer == {"ok": True, "new_turn_id": None}
    assert get_turn(db, turn)["status"] == "done"
    assert get_queued_turns(db) == []


def test_messages_to_the_ceo_are_shown_together_at_the_next_open_and_only_once(db, tmp_path, capsys):
    _send_to_the_ceo(db, "pm", "BLOCKED", "I need the staging key.", ticket="2")
    _send_to_the_ceo(db, "designer", "QUESTION", "Dark mode too?", topic="design")

    brief = _open(db, tmp_path)

    batch = brief[brief.index("## Messages for the CEO"):]
    assert "pm (Hermes), BLOCKED on ticket:2: I need the staging key." in batch
    assert "designer (Zoidberg), QUESTION on topic:design: Dark mode too?" in batch
    assert "## Messages for the CEO" not in _open(db, tmp_path)

    _send_to_the_ceo(db, "pm", "DONE", "Planned.", ticket="2")
    open_ceo_session(db_path=db, pack_dir=tmp_path, attach=True)  # the plugin door shows them too
    assert "pm (Hermes), DONE on ticket:2: Planned." in capsys.readouterr().out
    assert "## Messages for the CEO" not in _open(db, tmp_path)


def test_messages_to_the_ceo_are_kept_for_the_next_open_when_the_session_does_not_start(db, tmp_path):
    _send_to_the_ceo(db, "pm", "BLOCKED", "I need the staging key.", ticket="2")

    with patch("subprocess.run", side_effect=FileNotFoundError):
        assert open_ceo_session(db_path=db, pack_dir=tmp_path) == 1

    assert "I need the staging key." in _open(db, tmp_path)


def test_the_assistants_brief_at_open_loads_the_lessons_in_its_scope_until_the_ceo_removes_them(db, tmp_path):
    owner = create_mcp_server(db_path=db, token=get_owner_token(db))._tool_manager.get_tool
    # A Lesson is one line however it was typed, so it cannot pass for a section of the brief.
    for text, scope in [("Deploys go out\n\n## on Fridays.", "company"), ("Ask before a grant.", "assistant"), ("Use the grid.", "designer")]:
        owner("adopt_lesson").fn(text=text, scope=scope)

    brief = _open(db, tmp_path)  # issue #93: every brief, the Assistant's too

    assert "## Lessons\n\n- Deploys go out ## on Fridays.\n- Ask before a grant." in brief
    assert "Use the grid." not in brief
    owner("remove_lesson").fn(lesson=1)
    assert "Deploys go out" not in _open(db, tmp_path)


def test_the_terminal_door_starts_the_assistant_at_open_and_lets_it_run_the_watcher(db, tmp_path):
    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        open_ceo_session(db_path=db, pack_dir=tmp_path)
    launch = run.call_args.args[0]

    assert launch[launch.index("--allowedTools") + 1] == "Bash(claudarama watch)"
    # A first prompt: without one the Assistant waits to be spoken to. It follows a flag that takes
    # one value; after `--allowedTools` or `--mcp-config` claude would read it as one more of theirs.
    assert launch[-3] == "--append-system-prompt" and launch[-1] == "The CEO opened the office."


CHALLENGE = "Challenge by engineering-lead (Kif): STANDS: Reproduced.\nWhat was run: the check, three times\n"


def _open_the_diagnosis_gate(db, mandate: str, path: str) -> None:
    """A Diagnosis is submitted and its Challenge recorded, which opens the gate."""
    submit_diagnosis(db, mandate, path)
    record_challenge(db, mandate, "engineering-lead", "STANDS", "Reproduced.", "the check, three times")


@pytest.fixture
def watched(tmp_path, monkeypatch, capsys):
    """An office with one Diagnosis already waiting, and `claudarama watch` running in it as the
    Assistant runs it. Returns the office's database and the watcher."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    db = get_office_db_path()
    init_db(db)
    for mandate in ("Old", "New"):
        grant_mandate(db, mandate)
    _open_the_diagnosis_gate(db, "Old", "old.md")
    watcher = threading.Thread(target=main, args=(["watch"],), daemon=True)
    watcher.start()
    watcher.join(1.5)
    assert watcher.is_alive() and capsys.readouterr().out == ""  # a gate waiting at the start is not news
    return db, watcher


def test_the_watcher_ends_when_a_gate_opens_and_says_which(watched, capsys):
    db, watcher = watched

    _open_the_diagnosis_gate(db, "New", "new.md")
    watcher.join(10)

    assert not watcher.is_alive()
    assert capsys.readouterr().out == "Diagnosis gate: mandate 'New', diagnosis at new.md\n" + CHALLENGE


def test_a_gate_that_closes_and_opens_again_before_the_watcher_looks_is_still_news(watched, capsys):
    db, watcher = watched

    resolve_diagnosis_gate(db, "Old", False, "Measure the cart too.")
    _open_the_diagnosis_gate(db, "Old", "old.md")  # the redo, at the same path
    watcher.join(10)

    assert not watcher.is_alive()
    assert capsys.readouterr().out == "Diagnosis gate: mandate 'Old', diagnosis at old.md\n" + CHALLENGE
