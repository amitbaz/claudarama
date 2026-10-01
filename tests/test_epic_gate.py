"""The Epic gate: PLANNING to EXECUTING, paused for the CEO (issue #71)."""
import sqlite3
from types import SimpleNamespace

import pytest

from claudarama.daemon import create_mcp_server
from claudarama.db import (
    epic_gates, get_owner_token, get_queued_turns, grant_mandate, init_db, queue_turn,
    register_ticket, submit_diagnosis,
    resolve_diagnosis_gate,
)
from claudarama.session import review_epic_gates


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "office.db"
    init_db(path)
    grant_mandate(path, "M1")
    submit_diagnosis(path, "M1", "d.md")
    resolve_diagnosis_gate(path, "M1", approved=True)
    return path


def _submit(db, tickets=("T1", "T2"), mandate="M1"):
    ctx = SimpleNamespace(request_context=SimpleNamespace(
        request=SimpleNamespace(path_params={"token": get_owner_token(db)})))
    server = create_mcp_server(db_path=db)
    return server._tool_manager.get_tool("submit_epic").fn(
        mandate=mandate, tickets=list(tickets), ctx=ctx)


def _state(db):
    with sqlite3.connect(db) as conn:
        return conn.execute("SELECT status, blocked_on_ceo FROM mandates").fetchone()


def _tickets(db):
    with sqlite3.connect(db) as conn:
        return [r[0] for r in conn.execute("SELECT id FROM tickets WHERE mandate_id = 'M1' ORDER BY id")]


def test_epic_ties_tickets_pauses_mandate_and_scheduler_skips_them(db):
    _submit(db)
    assert _state(db) == ("EXECUTING", 1)
    assert _tickets(db) == ["T1", "T2"]
    queue_turn(db, "fullstack-engineer", thread="ticket:T1")
    assert get_queued_turns(db) == []


def test_epic_refused_outside_planning_or_while_diagnosis_pending_or_empty(db):
    with pytest.raises(ValueError, match="at least one ticket"):
        _submit(db, tickets=())
    _submit(db)
    with pytest.raises(ValueError, match="not PLANNING and unblocked"):
        _submit(db)
    grant_mandate(db, "M2")
    submit_diagnosis(db, "M2", "d2.md")  # still paused at the Diagnosis gate
    with pytest.raises(ValueError, match="not PLANNING and unblocked"):
        _submit(db, tickets=["X"], mandate="M2")


def test_yes_unblocks_and_work_can_start(db):
    _submit(db)
    assert not review_epic_gates(db, ask=lambda _: "yes")
    assert _state(db) == ("EXECUTING", 0)
    queue_turn(db, "fullstack-engineer", thread="ticket:T1")
    assert len(get_queued_turns(db)) == 1


def test_discuss_stays_paused_and_no_discards_the_drafted_tickets(db):
    _submit(db)
    assert review_epic_gates(db, ask=lambda _: "discuss")
    assert _state(db) == ("EXECUTING", 1)
    answers = iter(["maybe", "no"])
    review_epic_gates(db, ask=lambda _: next(answers))
    assert _state(db) == ("PLANNING", 0)
    assert _tickets(db) == []


def test_epic_cannot_take_an_existing_ticket(db):
    register_ticket(db, "T1", "M1")
    with pytest.raises(ValueError, match="already exists"):
        _submit(db)
    assert _state(db) == ("PLANNING", 0)  # refused whole: nothing paused


def test_no_keeps_tickets_that_predate_the_epic(db):
    register_ticket(db, "OLD", "M1")
    _submit(db)
    review_epic_gates(db, ask=lambda _: "no")
    assert _tickets(db) == ["OLD"]


def test_epic_gate_lists_only_drafted_tickets(db):
    register_ticket(db, "OLD", "M1")
    _submit(db)
    assert epic_gates(db) == [{"id": "M1", "tickets": ["T1", "T2"]}]
