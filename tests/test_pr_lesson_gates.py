"""The PR gate and the Lesson gate: EXECUTING to LEARNING to CLOSED (issue #73)."""
import json
import sqlite3
import subprocess

import pytest

from claudarama.daemon import create_mcp_server
from claudarama.db import (
    get_owner_token, get_queued_turns, grant_mandate, init_db, queue_turn, record_verdict,
    register_ticket, submit_diagnosis,
)
from claudarama.session import advance_to_learning, review_lesson_gates, review_pr_gates

HEAD = "abc123"


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "office.db"
    init_db(path)
    grant_mandate(path, "M1")
    submit_diagnosis(path, "M1", "d.md")
    register_ticket(path, "11", "M1")
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE mandates SET status = 'EXECUTING', blocked_on_ceo = 0 WHERE id = 'M1'")
    return path


class FakeGh:
    """Stands in for `gh`: one open PR 7 closing issue 11; records every call."""

    def __init__(self, prs=None, issue_state="CLOSED"):
        self.prs = prs if prs is not None else [
            {"number": 7, "title": "Fix it", "headRefOid": HEAD, "closingIssuesReferences": [{"number": 11}]}]
        self.issue_state = issue_state
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        if args[:2] == ["pr", "list"]:
            return json.dumps(self.prs)
        if args[:2] == ["issue", "view"]:
            return json.dumps({"state": self.issue_state})
        return ""

    def mutations(self):
        return [c for c in self.calls if c[:2] in (["pr", "merge"], ["pr", "close"])]


def _ship(db, verdict="SHIP", head=HEAD):
    record_verdict(db, 7, head, "engineering-lead", verdict, "d.md", "uv run pytest")


def _state(db):
    with sqlite3.connect(db) as conn:
        return conn.execute("SELECT status, blocked_on_ceo FROM mandates WHERE id = 'M1'").fetchone()


# --- PR gate ---------------------------------------------------------------


def test_yes_merges_a_pr_with_a_ship_verdict_for_its_head_commit(db):
    _ship(db)
    gh = FakeGh()
    assert not review_pr_gates(db, gh, ask=lambda _: "yes")
    assert gh.mutations() == [["pr", "merge", "7", "--merge", "--match-head-commit", HEAD]]


@pytest.mark.parametrize("setup", ["none", "fail", "stale_head"])
def test_yes_is_blocked_without_a_ship_verdict_for_the_head_commit(db, capsys, setup):
    if setup == "fail":
        _ship(db, "FAIL")
    if setup == "stale_head":
        _ship(db, "SHIP", head="older")
    gh = FakeGh()
    review_pr_gates(db, gh, ask=lambda _: "yes")
    assert gh.mutations() == []
    assert "no SHIP verdict" in capsys.readouterr().out


def test_gh_failure_skips_the_gates_instead_of_crashing(db, capsys):
    def broken(args):
        raise subprocess.CalledProcessError(1, "gh")
    assert not review_pr_gates(db, broken, ask=lambda _: "yes")
    advance_to_learning(db, broken)
    assert _state(db) == ("EXECUTING", 0)
    assert capsys.readouterr().err.count("gh failed") == 2


def test_no_closes_the_pr_and_discuss_leaves_it_alone(db):
    _ship(db)
    gh = FakeGh()
    assert review_pr_gates(db, gh, ask=lambda _: "discuss")
    assert gh.mutations() == []
    review_pr_gates(db, gh, ask=lambda _: "no")
    assert [m[:3] for m in gh.mutations()] == [["pr", "close", "7"]]


def test_gate_lists_only_prs_that_close_office_tickets(db):
    gh = FakeGh(prs=[{"number": 8, "title": "Unrelated", "headRefOid": "x", "closingIssuesReferences": []}])
    asked = []
    review_pr_gates(db, gh, ask=lambda q: asked.append(q) or "yes")
    assert asked == [] and gh.mutations() == []


def _answer_in_the_session(db, gh, gate, answer, **reason):
    server = create_mcp_server(db_path=db, token=get_owner_token(db), gh=gh)
    return server._tool_manager.get_tool("answer_gate").fn(gate=gate, answer=answer, **reason)


def test_inside_the_session_a_yes_without_a_ship_verdict_is_refused_and_nothing_is_merged(db):
    gh = FakeGh()
    with pytest.raises(PermissionError, match="no SHIP verdict for head commit abc123 of PR #7"):
        _answer_in_the_session(db, gh, "pr:7", "YES")
    assert gh.mutations() == []


def test_inside_the_session_a_no_needs_its_reason_and_closes_the_pr_only_with_one(db):
    gh = FakeGh()
    with pytest.raises(ValueError, match="a NO needs a one-line reason"):
        _answer_in_the_session(db, gh, "pr:7", "NO")
    assert gh.mutations() == []
    _answer_in_the_session(db, gh, "pr:7", "NO", reason="It still loads every image.")
    assert [m[:3] for m in gh.mutations()] == [["pr", "close", "7"]]


def test_inside_the_session_an_answer_must_be_yes_no_or_discuss_at_a_gate_that_is_open(db):
    gh = FakeGh()
    with pytest.raises(ValueError, match="not YES, NO or DISCUSS"):
        _answer_in_the_session(db, gh, "pr:7", "MAYBE")
    with pytest.raises(ValueError, match="no open gate 'epic:M1'; the open gates are: pr:7"):
        _answer_in_the_session(db, gh, "epic:M1", "YES")
    assert _answer_in_the_session(db, gh, "pr:7", "discuss") == {"ok": True, "gate": "pr:7", "answer": "DISCUSS", "open": True}
    assert gh.mutations() == []


def test_mandate_moves_to_learning_only_once_all_its_tickets_are_closed(db):
    advance_to_learning(db, FakeGh(issue_state="OPEN"))
    assert _state(db) == ("EXECUTING", 0)
    advance_to_learning(db, FakeGh(issue_state="CLOSED"))
    assert _state(db) == ("LEARNING", 0)


def test_a_paused_mandate_does_not_advance(db):
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE mandates SET blocked_on_ceo = 1")
    advance_to_learning(db, FakeGh())
    assert _state(db) == ("EXECUTING", 1)


# --- Lesson gate -----------------------------------------------------------


def _submit_lessons(db, mandate="M1", token=None):
    server = create_mcp_server(db_path=db, token=token or get_owner_token(db))
    return server._tool_manager.get_tool("submit_lessons").fn(
        mandate=mandate, lesson_path="docs/lessons/m1.md")


@pytest.fixture
def learning(db):
    advance_to_learning(db, FakeGh())
    return db


def test_submit_lessons_closes_the_mandate_and_pauses_it_for_the_ceo(learning):
    assert _submit_lessons(learning)["status"] == "CLOSED"
    assert _state(learning) == ("CLOSED", 1)
    with sqlite3.connect(learning) as conn:
        assert conn.execute("SELECT lesson_path FROM mandates").fetchone() == ("docs/lessons/m1.md",)
    queue_turn(learning, "fullstack-engineer", thread="ticket:11")
    assert get_queued_turns(learning) == []


def test_submit_lessons_refused_unless_learning_and_unblocked(db):
    with pytest.raises(ValueError, match="not LEARNING"):
        _submit_lessons(db)  # still EXECUTING
    with pytest.raises(PermissionError):
        _submit_lessons(db, token="nope")


def test_lesson_yes_finalizes_the_mandate(learning):
    _submit_lessons(learning)
    assert not review_lesson_gates(learning, ask=lambda _: "yes")
    assert _state(learning) == ("CLOSED", 0)
    with pytest.raises(ValueError, match="not LEARNING"):
        _submit_lessons(learning)  # nothing reopens a closed mandate


def test_lesson_discuss_stays_paused_and_no_sends_it_back_to_learning(learning):
    _submit_lessons(learning)
    assert review_lesson_gates(learning, ask=lambda _: "discuss")
    assert _state(learning) == ("CLOSED", 1)
    answers = iter(["maybe", "no", "Too vague."])
    review_lesson_gates(learning, ask=lambda _: next(answers))
    assert _state(learning) == ("LEARNING", 0)
    _submit_lessons(learning)  # can resubmit
