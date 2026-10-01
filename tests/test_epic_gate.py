"""The Epic gate: PLANNING to EXECUTING, paused for the CEO (issue #71)."""
import sqlite3

import pytest

from claudarama.daemon import create_mcp_server
from claudarama.db import (
    epic_gates, get_owner_token, get_queued_turns, grant_mandate, init_db, list_turns, queue_turn,
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


ROLES = {"T1": "fullstack-engineer", "T2": "designer", "X": "pm"}


def _submit(db, tickets=("T1", "T2"), mandate="M1", roles=ROLES):
    """Submit an Epic of *tickets*, each naming its Role."""
    server = create_mcp_server(db_path=db, token=get_owner_token(db))
    return server._tool_manager.get_tool("submit_epic").fn(
        mandate=mandate, tickets={ticket: roles[ticket] for ticket in tickets})


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


def test_yes_unblocks_and_queues_a_turn_for_each_tickets_role(db):
    _submit(db)
    assert list_turns(db) == []  # nobody starts on a drafted ticket
    assert not review_epic_gates(db, ask=lambda _: "yes")
    assert _state(db) == ("EXECUTING", 0)
    assert [(t["person_id"], t["thread"]) for t in list_turns(db)] == [
        ("fullstack-engineer", "ticket:T1"), ("designer", "ticket:T2")]
    assert len(get_queued_turns(db)) == 2  # and they can start


@pytest.mark.parametrize("role", ["copywriter", "", "../office-rules", "ceo"])
def test_an_epic_naming_a_role_with_no_role_file_is_refused_whole(db, role):
    with pytest.raises(ValueError, match="a Role with no role file"):
        _submit(db, roles={"T1": "designer", "T2": role})
    assert _state(db) == ("PLANNING", 0)
    assert _tickets(db) == []


def test_the_epic_gate_shows_each_tickets_role(db, capsys):
    _submit(db)
    review_epic_gates(db, ask=lambda _: "discuss")
    assert "  - T1: fullstack-engineer (Bender)\n  - T2: designer (Zoidberg)\n" in capsys.readouterr().out


def test_discuss_stays_paused_and_no_discards_the_drafted_tickets(db):
    _submit(db)
    assert review_epic_gates(db, ask=lambda _: "discuss")
    assert _state(db) == ("EXECUTING", 1)
    answers = iter(["maybe", "no", "Too broad."])
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
    assert epic_gates(db) == [{"id": "M1", "tickets": {"T1": "fullstack-engineer", "T2": "designer"}}]
