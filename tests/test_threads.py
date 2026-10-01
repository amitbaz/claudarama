"""Threads per ticket or topic (issue #33), tested through the `send` MCP tool.

A thread is the messages about one ticket, or one topic when there is no
ticket. The turn a message wakes records its thread, and that turn's brief
loads only that thread.
"""
import asyncio
import sqlite3
from pathlib import Path

import pytest

from claudarama.daemon import make_send_tool
from claudarama.db import Identity, get_turn, init_db, queue_turn
from claudarama.supervisor import Supervisor


def _office(tmp_path: Path) -> tuple[Path, Path]:
    db_path = tmp_path / "office.db"
    init_db(db_path)
    pack = tmp_path / ".claudarama"
    (pack / "profiles").mkdir(parents=True)
    (pack / "company.md").write_text("# Test Co\n")
    return db_path, pack


def _send(db_path, sender, receiver, body, **kw) -> dict:
    turn_id = queue_turn(db_path, person_id=sender)
    return asyncio.run(
        make_send_tool(db_path)(
            identity=Identity("turn", sender, turn_id),
            receiver_id=receiver,
            msg_type="DONE",
            body=body,
            **kw,
        )
    )


def _brief_for(db_path, pack, turn_id) -> str:
    sup = Supervisor(db_path, pack, pack, claude_binary="claude")
    return sup.build_launch(get_turn(db_path, turn_id)).brief


def test_send_refuses_message_with_neither_ticket_nor_topic(tmp_path):
    db_path, _ = _office(tmp_path)
    turn_id = queue_turn(db_path, person_id="fullstack-engineer")
    with pytest.raises(ValueError):
        asyncio.run(
            make_send_tool(db_path)(
                identity=Identity("turn", "fullstack-engineer", turn_id),
                receiver_id="pm",
                msg_type="DONE",
                body="hi",
            )
        )
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
    assert get_turn(db_path, turn_id)["status"] == "queued"  # sender turn not ended


def test_two_tickets_between_same_people_stay_in_separate_threads(tmp_path):
    db_path, pack = _office(tmp_path)
    _send(db_path, "fullstack-engineer", "pm", "about auth", ticket="T-1")
    r = _send(db_path, "fullstack-engineer", "pm", "about billing", ticket="T-2")

    brief = _brief_for(db_path, pack, r["new_turn_id"])
    assert "about billing" in brief
    assert "about auth" not in brief


def test_topic_thread_when_no_ticket(tmp_path):
    db_path, pack = _office(tmp_path)
    _send(db_path, "fullstack-engineer", "pm", "lunch plans", topic="offsite")
    r = _send(db_path, "fullstack-engineer", "pm", "ticket news", ticket="T-1")
    r2 = _send(db_path, "pm", "fullstack-engineer", "offsite reply", topic="offsite")

    brief = _brief_for(db_path, pack, r2["new_turn_id"])
    assert "lunch plans" in brief and "offsite reply" in brief
    assert "ticket news" not in brief
    assert "lunch plans" not in _brief_for(db_path, pack, r["new_turn_id"])


def test_reply_turn_records_thread_that_woke_it(tmp_path):
    db_path, _ = _office(tmp_path)
    a = _send(db_path, "fullstack-engineer", "pm", "x", ticket="T-1")
    b = _send(db_path, "fullstack-engineer", "pm", "y", topic="offsite")
    assert get_turn(db_path, a["new_turn_id"])["thread"] == "ticket:T-1"
    assert get_turn(db_path, b["new_turn_id"])["thread"] == "topic:offsite"


def test_old_database_keeps_working(tmp_path):
    """A DB made before threads existed migrates: old ticket messages join their ticket thread."""
    db_path = tmp_path / "office.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE people (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL, level INTEGER NOT NULL DEFAULT 1, manager_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE turns (id TEXT PRIMARY KEY, person_id TEXT NOT NULL,
                status TEXT NOT NULL, thread_with TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, ended_at TIMESTAMP);
            CREATE TABLE messages (id TEXT PRIMARY KEY, sender TEXT NOT NULL,
                receiver TEXT NOT NULL, msg_type TEXT NOT NULL, ticket TEXT,
                body TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            INSERT INTO messages (id, sender, receiver, msg_type, ticket, body)
                VALUES ('m1','fullstack-engineer','pm','DONE','T-1','old note');
            """
        )
    init_db(db_path)
    pack = tmp_path / ".claudarama"
    (pack / "profiles").mkdir(parents=True)
    r = _send(db_path, "fullstack-engineer", "pm", "new note", ticket="T-1")
    brief = _brief_for(db_path, pack, r["new_turn_id"])
    assert "old note" in brief and "new note" in brief
