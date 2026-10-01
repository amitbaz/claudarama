"""The record_ship_check tool: a Ship-check verdict tied to its Diagnosis (issue #72)."""
import sqlite3
from types import SimpleNamespace

import pytest

from claudarama.daemon import create_mcp_server
from claudarama.db import get_owner_token, init_db


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "office.db"
    init_db(path)
    return path


def _ship_check(db, **args):
    ctx = SimpleNamespace(request_context=SimpleNamespace(
        request=SimpleNamespace(path_params={"token": get_owner_token(db)})))
    tool = create_mcp_server(db_path=db)._tool_manager.get_tool("record_ship_check")
    return tool.fn(ctx=ctx, **args)


def _rows(db):
    with sqlite3.connect(db) as conn:
        return conn.execute(
            "SELECT pull_request, head_commit, reviewer_id, verdict, diagnosis_path, command FROM verdicts"
        ).fetchall()


GOOD = dict(pull_request=7, head_commit="abc123", verdict="SHIP",
            diagnosis_path="docs/diagnoses/m1.md", command="uv run pytest")


def test_records_verdict_with_diagnosis_and_command(db):
    assert _ship_check(db, **GOOD)["ok"]
    assert _rows(db) == [(7, "abc123", "ceo", "SHIP", "docs/diagnoses/m1.md", "uv run pytest")]


def test_rerun_on_same_head_replaces_the_verdict(db):
    _ship_check(db, **{**GOOD, "verdict": "FAIL"})
    _ship_check(db, **GOOD)
    assert [r[3] for r in _rows(db)] == ["SHIP"]


@pytest.mark.parametrize("bad", [
    {"verdict": "MAYBE"}, {"diagnosis_path": " "}, {"command": ""},
])
def test_refuses_unknown_verdict_and_missing_evidence(db, bad):
    with pytest.raises(ValueError):
        _ship_check(db, **{**GOOD, **bad})
    assert _rows(db) == []
