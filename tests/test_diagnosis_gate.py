"""Mandate state machine and the Diagnosis gate (issue #70)."""
import sqlite3

import pytest

from claudarama.daemon import create_mcp_server
from claudarama.db import (
    get_owner_token, get_queued_turns, grant_mandate, init_db, queue_turn, record_challenge, register_ticket,
)
from claudarama.session import review_diagnosis_gates


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "office.db"
    init_db(path)
    grant_mandate(path, "M1")
    register_ticket(path, "T1", "M1")
    return path


DIAGNOSIS = ".claudarama/company/diagnoses/d.md"


def _submit(db):
    """Submit the Diagnosis and record the Challenge that opens its gate."""
    server = create_mcp_server(db_path=db, token=get_owner_token(db))
    server._tool_manager.get_tool("submit_diagnosis").fn(mandate="M1", diagnosis_path=DIAGNOSIS)
    record_challenge(db, "M1", "engineering-lead", "STANDS", "Reproduced.", "the check, three times")


def _state(db):
    with sqlite3.connect(db) as conn:
        return conn.execute("SELECT status, blocked_on_ceo, diagnosis_path FROM mandates").fetchone()


def test_diagnosis_pauses_mandate_and_scheduler_skips_it(db):
    queue_turn(db, "fullstack-engineer", thread="ticket:T1")
    assert len(get_queued_turns(db)) == 1
    _submit(db)
    assert _state(db) == ("PLANNING", 1, DIAGNOSIS)
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


def test_a_challenge_needs_a_submitted_diagnosis_a_verdict_its_reasons_and_what_was_run(db):
    def challenge(verdict="STANDS", reasons="Reproduced.", ran="the check, three times"):
        record_challenge(db, "M1", "engineering-lead", verdict, reasons, ran)

    with pytest.raises(ValueError, match="no Diagnosis waiting for a Challenge"):
        challenge()
    create_mcp_server(db_path=db, token=get_owner_token(db))._tool_manager.get_tool("submit_diagnosis").fn(
        mandate="M1", diagnosis_path=DIAGNOSIS)
    with pytest.raises(ValueError, match="STANDS or DISPUTED"):
        challenge(verdict="SHIP")
    with pytest.raises(ValueError, match="its reasons and what the challenger ran"):
        challenge(reasons=" ")
    with pytest.raises(ValueError, match="its reasons and what the challenger ran"):
        challenge(ran="")
    assert _state(db)[:2] == ("INVESTIGATING", 0)  # nothing refused opened the gate
    challenge()
    assert _state(db)[:2] == ("PLANNING", 1)
    with pytest.raises(ValueError, match="no Diagnosis waiting for a Challenge"):
        challenge()  # one Challenge per submission
