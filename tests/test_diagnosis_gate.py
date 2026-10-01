"""Mandate state machine and the Diagnosis gate (issue #70)."""
import sqlite3

import pytest

from claudarama.daemon import create_mcp_server
from claudarama.db import (
    get_owner_token, get_queued_turns, grant_mandate, init_db, queue_turn, register_ticket,
)
from claudarama.session import review_diagnosis_gates


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "office.db"
    init_db(path)
    grant_mandate(path, "M1")
    register_ticket(path, "T1", "M1")
    return path


def _submit(db):
    server = create_mcp_server(db_path=db, token=get_owner_token(db))
    return server._tool_manager.get_tool("submit_diagnosis").fn(
        mandate="M1", diagnosis_path="d.md")


def _state(db):
    with sqlite3.connect(db) as conn:
        return conn.execute("SELECT status, blocked_on_ceo, diagnosis_path FROM mandates").fetchone()


def test_diagnosis_pauses_mandate_and_scheduler_skips_it(db):
    queue_turn(db, "fullstack-engineer", thread="ticket:T1")
    assert len(get_queued_turns(db)) == 1
    _submit(db)
    assert _state(db) == ("PLANNING", 1, "d.md")
    assert get_queued_turns(db) == []
    with pytest.raises(ValueError, match="not INVESTIGATING"):
        _submit(db)


def test_yes_unblocks(db):
    queue_turn(db, "fullstack-engineer", thread="ticket:T1")
    _submit(db)
    assert not review_diagnosis_gates(db, ask=lambda _: "yes")
    assert _state(db)[:2] == ("PLANNING", 0)  # planning begins; the Epic gate comes next
    assert len(get_queued_turns(db)) == 1


def test_no_returns_to_investigating_and_discuss_stays_paused(db):
    _submit(db)
    assert review_diagnosis_gates(db, ask=lambda _: "discuss")
    assert _state(db)[:2] == ("PLANNING", 1)
    answers = iter(["maybe", "no", "", "The cart is slow."])  # a NO is asked for its reason until it has one
    review_diagnosis_gates(db, ask=lambda _: next(answers))
    assert _state(db)[:2] == ("INVESTIGATING", 0)
