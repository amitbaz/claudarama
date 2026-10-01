"""The record_ship_check tool: a Ship-check verdict tied to its Diagnosis (issue #72)."""
import sqlite3

import pytest

from claudarama.daemon import create_mcp_server
from claudarama.db import (
    create_turn_token, get_owner_token, grant_mandate, init_db, mark_turn_running, queue_turn,
    ship_checked, submit_diagnosis,
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
    _ship_check(db, **{**GOOD, "verdict": "FAIL"})
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
