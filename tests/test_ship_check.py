"""The record_ship_check tool: a Ship-check verdict tied to its Diagnosis (issue #72)."""
import sqlite3

import pytest

from claudarama.daemon import create_mcp_server
from claudarama.db import (
    create_turn_token, get_owner_token, get_queued_turns, get_thread, get_turn, grant_mandate, init_db,
    mandate_states, mark_turn_running, queue_turn, record_challenge, record_verdict, resolve_diagnosis_gate,
    resolve_epic_gate,
    ship_checked, submit_diagnosis, submit_epic,
)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "office.db"
    init_db(path)
    grant_mandate(path, "M1")
    submit_diagnosis(path, "M1", "docs/diagnoses/m1.md")
    return path


def _token(db, caller):
    if caller == "ceo":
        return get_owner_token(db)
    turn_id = queue_turn(db, caller, kind="ritual")
    mark_turn_running(db, turn_id)
    return create_turn_token(db, turn_id)


def _ship_check(db, caller="engineering-lead", **args):
    tool = create_mcp_server(db_path=db, token=_token(db, caller))._tool_manager.get_tool("record_ship_check")
    return tool.fn(**args)


def _rows(db):
    with sqlite3.connect(db) as conn:
        return conn.execute(
            "SELECT pull_request, head_commit, reviewer_id, verdict, diagnosis_path, command FROM verdicts"
        ).fetchall()


GOOD = dict(pull_request=7, head_commit="abc123", verdict="SHIP",
            diagnosis_path="docs/diagnoses/m1.md", command="uv run pytest")


def test_records_verdict_with_diagnosis_and_command(db):
    assert _ship_check(db, **GOOD)["ok"]
    assert _rows(db) == [(7, "abc123", "engineering-lead", "SHIP", "docs/diagnoses/m1.md", "uv run pytest")]
    assert ship_checked(db, 7, "abc123")


@pytest.mark.parametrize("caller", ["fullstack-engineer", "eval-engineer", "assistant", "ceo"])
def test_a_verdict_from_anyone_but_the_engineering_lead_is_refused(db, caller):
    with pytest.raises(PermissionError, match="only from the engineering-lead"):
        _ship_check(db, caller, **GOOD)
    assert not ship_checked(db, 7, "abc123")


def test_rerun_on_same_head_replaces_the_verdict(db):
    _ship_check(db, **{**GOOD, "verdict": "FAIL", "reason": "Not fixed."})
    _ship_check(db, **GOOD)
    assert [r[3] for r in _rows(db)] == ["SHIP"]


@pytest.mark.parametrize("bad", [
    {"verdict": "MAYBE"}, {"diagnosis_path": " "}, {"command": ""},
    {"diagnosis_path": "docs/diagnoses/made-up.md"},
])
def test_refuses_unknown_verdict_missing_evidence_and_unlinked_diagnosis(db, bad):
    with pytest.raises(ValueError):
        _ship_check(db, **{**GOOD, **bad})
    assert _rows(db) == []


def test_init_db_adds_evidence_columns_to_an_old_verdicts_table(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE verdicts (pull_request INTEGER NOT NULL, head_commit TEXT NOT NULL, "
            "reviewer_id TEXT NOT NULL, verdict TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "PRIMARY KEY (pull_request, head_commit, reviewer_id))")
        conn.execute("INSERT INTO verdicts (pull_request, head_commit, reviewer_id, verdict) VALUES (1, 'a', 'x', 'SHIP')")
    init_db(path)
    assert _rows(path) == [(1, "a", "x", "SHIP", None, None)]


# --- a FAIL goes back to the ticket's Role; its second FAIL stops the ticket (issue #90) ---


@pytest.fixture
def executing(tmp_path):
    """A mandate the researcher investigated on ticket 1, with an approved Epic: ticket 2 is the
    designer's and ticket 3 the frontend-engineer's. Every turn queued on the way has ended."""
    path = tmp_path / "office.db"
    init_db(path)
    grant_mandate(path, "M1", "1")
    _diagnose(path, "docs/diagnoses/m1.md")
    resolve_diagnosis_gate(path, "M1", True)
    submit_epic(path, "M1", {"2": "designer", "3": "frontend-engineer"})
    resolve_epic_gate(path, "M1", True)
    _end_turns(path)
    return path


def _diagnose(db, path):
    """A Diagnosis is submitted and its Challenge recorded: the mandate waits at the Diagnosis gate."""
    submit_diagnosis(db, "M1", path)
    record_challenge(db, "M1", "engineering-lead", "STANDS", "Reproduced.", "the check, three times")


def _end_turns(db):
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE turns SET status = 'done'")


def _fail(db, pull_request, reason, ticket="2"):
    return record_verdict(
        db, pull_request, f"head-{pull_request}", "engineering-lead", "FAIL", "docs/diagnoses/m1.md", "pytest", reason, ticket)


def _waiting(db):
    """Who the office would start now, and on which thread."""
    return [(get_turn(db, t["id"])["person_id"], get_turn(db, t["id"])["thread"]) for t in get_queued_turns(db)]


def _status(db):
    return mandate_states(db)[0]["status"]


def test_a_fail_without_a_reason_is_refused_and_nothing_is_recorded(executing):
    with pytest.raises(ValueError, match="a FAIL needs a one-line reason"):
        _fail(executing, 7, "  ")
    assert _rows(executing) == [] and _waiting(executing) == []


def test_a_fail_wakes_the_tickets_role_with_the_reason(executing):
    assert _fail(executing, 7, "The page still\ntakes four seconds.") is None
    assert _waiting(executing) == [("designer", "ticket:2")]
    assert [(m["sender"], m["receiver"], m["msg_type"], m["body"]) for m in get_thread(executing, "ticket:2")] == [
        ("engineering-lead", "designer", "FAIL", "Ship-check of #7: The page still takes four seconds.")]
    assert _status(executing) == "EXECUTING"


def test_a_tickets_second_fail_stops_it_and_wakes_the_investigating_role_with_both_reasons(executing):
    _fail(executing, 7, "Still slow.")
    _end_turns(executing)
    told = _fail(executing, 8, "Fast, but inside the spread.")
    assert told == "Ticket 2 failed its Ship-check 2 times: mandate 'M1' is back with the researcher (Amy)"
    assert _status(executing) == "INVESTIGATING"
    assert _waiting(executing) == [("researcher", "ticket:1")]  # no further turn for the designer
    assert [(m["receiver"], m["msg_type"], m["body"]) for m in get_thread(executing, "ticket:1")][-1:] == [(
        "researcher", "STOPPED",
        "Ticket 2 failed its Ship-check 2 times. 1) Ship-check of #7: Still slow. 2) Ship-check of #8: Fast, but inside the spread.",
    )]


def test_a_fail_on_another_ticket_is_that_tickets_first(executing):
    _fail(executing, 7, "Still slow.")
    assert _fail(executing, 9, "Misaligned.", ticket="3") is None
    assert _status(executing) == "EXECUTING"
    assert set(_waiting(executing)) == {("designer", "ticket:2"), ("frontend-engineer", "ticket:3")}


def test_work_on_the_mandates_tickets_waits_until_a_revised_diagnosis_passes_the_gate(executing):
    _fail(executing, 7, "Still slow.")
    _end_turns(executing)
    queue_turn(executing, "frontend-engineer", thread="ticket:3")
    _fail(executing, 8, "Fast, but inside the spread.")
    assert _waiting(executing) == [("researcher", "ticket:1")]  # ticket 3 waits too

    _end_turns_of(executing, "researcher")
    submit_diagnosis(executing, "M1", "docs/diagnoses/m1-revised.md")
    assert _waiting(executing) == [("engineering-lead", "ticket:1")]  # the Challenge, on the investigation ticket
    _end_turns_of(executing, "engineering-lead")
    record_challenge(executing, "M1", "engineering-lead", "STANDS", "Reproduced.", "the check, three times")
    assert _waiting(executing) == []  # everything waits on the CEO
    resolve_diagnosis_gate(executing, "M1", True)
    assert set(_waiting(executing)) == {("pm", "ticket:1"), ("frontend-engineer", "ticket:3")}


def _end_turns_of(db, role):
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE turns SET status = 'done' WHERE person_id = ?", (role,))
