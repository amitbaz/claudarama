"""Grants on mandates (issue #35), through the MCP tools and supervisor seams."""
import sqlite3

import pytest

from claudarama.daemon import create_mcp_server
from claudarama.db import (
    create_turn_token,
    get_owner_token,
    get_turn,
    init_db,
    mark_turn_running,
    queue_turn,
)
from claudarama.supervisor import Supervisor


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "office.db"
    init_db(path)
    with sqlite3.connect(path) as conn:
        conn.executemany(
            "INSERT INTO people (id, name, role) VALUES (?, ?, ?)",
            [("p1", "Bender", "engineer"), ("p2", "Leela", "assistant")],
        )
    return path


def _call(db, token, tool, args):
    """Call an MCP tool as the holder of *token*, without an HTTP server."""
    from types import SimpleNamespace

    server = create_mcp_server(db_path=db)
    ctx = SimpleNamespace(
        request_context=SimpleNamespace(request=SimpleNamespace(path_params={"token": token}))
    )
    return server._tool_manager.get_tool(tool).fn(**args, ctx=ctx)


def _turn_token(db):
    turn_id = queue_turn(db, "p1")
    mark_turn_running(db, turn_id)
    return create_turn_token(db, turn_id)


def _run(db, tmp_path, turn_id):
    (tmp_path / "claude").write_text("#!/bin/sh\necho ok\n")
    (tmp_path / "claude").chmod(0o755)
    Supervisor(db, tmp_path / ".claudarama", tmp_path, claude_binary=str(tmp_path / "claude")).run_one_turn(turn_id)
    with sqlite3.connect(db) as conn:
        return conn.execute("SELECT status, refusal FROM turns WHERE id = ?", (turn_id,)).fetchone()


def test_only_owner_grants(db):
    with pytest.raises(PermissionError, match="owner"):
        _call(db, _turn_token(db), "grant", {"mandate": "M1"})
    assert _call(db, get_owner_token(db), "grant", {"mandate": "M1"})["ok"]


def test_ticket_needs_granted_mandate_and_can_be_hard(db):
    token = _turn_token(db)
    with pytest.raises(PermissionError, match="not granted"):
        _call(db, token, "ticket_ready", {"ticket": "T-1", "mandate": "M1"})
    _call(db, get_owner_token(db), "grant", {"mandate": "M1"})
    _call(db, token, "ticket_ready", {"ticket": "T-1", "mandate": "M1", "hard": True})
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT mandate_id, hard FROM tickets").fetchone() == ("M1", 1)


@pytest.mark.parametrize("thread", [None, "topic:x", "ticket:T-9"])
def test_ungranted_or_ticketless_turn_is_refused_with_reason(db, tmp_path, thread):
    status, refusal = _run(db, tmp_path, queue_turn(db, "p1", thread=thread))
    assert status == "refused" and refusal


def test_granted_ticket_turn_and_its_reply_start(db, tmp_path):
    _call(db, get_owner_token(db), "grant", {"mandate": "M1"})
    _call(db, _turn_token(db), "ticket_ready", {"ticket": "T-1", "mandate": "M1"})
    assert _run(db, tmp_path, queue_turn(db, "p1", thread="ticket:T-1"))[0] == "done"


def test_ritual_and_assistant_turns_need_no_mandate(db, tmp_path):
    assert _run(db, tmp_path, queue_turn(db, "p1", kind="ritual"))[0] == "done"
    assert _run(db, tmp_path, queue_turn(db, "p2"))[0] == "done"
