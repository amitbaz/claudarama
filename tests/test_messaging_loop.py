"""Tests for the Ephemeral Tools & Messaging Loop (issue #24).

Covers three seams per spec #21:

DB Seam (Slice 1)
-----------------
store_message and get_thread directly mutate and query the DB.

Brief Thread Injection (Slice 2)
---------------------------------
build_brief appends a ## Message Thread section when thread history exists.

``send`` MCP Tool Seam (Slice 3)
---------------------------------
The spec's MCP HTTP Seam is described as: "An HTTP client connects to the
in-memory/temp daemon and calls tools (e.g. send). We assert that the SQLite
DB mutates correctly." We test this at the tool-function level (via
make_send_tool) which exercises the same DB mutations. The send tool:
- stores the message,
- marks the sender's active turn done (clean end),
- queues a fresh turn for the receiver with a thread_with pointer so the
  supervisor injects the live thread into the brief.
"""
import asyncio
import sqlite3
from pathlib import Path

import pytest

from claudarama.db import init_db, queue_turn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _seed_person(
    db_path: Path,
    person_id: str = "p1",
    name: str = "Bender",
    role: str = "fullstack-engineer",
) -> str:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO people (id, name, role) VALUES (?, ?, ?)",
            (person_id, name, role),
        )
    return person_id


def _setup_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "office.db"
    init_db(db_path)
    _seed_person(db_path, "p1", name="Bender", role="fullstack-engineer")
    _seed_person(db_path, "p2", name="Leela", role="cpo")
    return db_path


# ---------------------------------------------------------------------------
# Slice 1: store_message + get_thread (DB layer)
# ---------------------------------------------------------------------------


class TestStoreAndRetrieveMessages:
    """DB-level: store a message and read back its thread."""

    def test_store_message_persists_to_db(self, tmp_path):
        from claudarama.db import store_message

        db_path = tmp_path / "office.db"
        init_db(db_path)

        msg_id = store_message(
            db_path,
            sender="bender",
            receiver="leela",
            msg_type="START",
            body="Hey, got a ticket for you",
        )
        assert msg_id  # non-empty

        with _connect(db_path) as conn:
            row = conn.execute(
                "SELECT sender, receiver, msg_type, body FROM messages WHERE id = ?",
                (msg_id,),
            ).fetchone()

        assert row["sender"] == "bender"
        assert row["receiver"] == "leela"
        assert row["msg_type"] == "START"
        assert "ticket" in row["body"]

    def test_store_message_with_ticket_persists_ticket(self, tmp_path):
        from claudarama.db import store_message

        db_path = tmp_path / "office.db"
        init_db(db_path)

        store_message(
            db_path,
            sender="bender",
            receiver="leela",
            msg_type="BLOCKED",
            body="Stuck on auth",
            ticket="T-42",
        )

        with _connect(db_path) as conn:
            row = conn.execute(
                "SELECT ticket FROM messages WHERE receiver = 'leela'",
            ).fetchone()
        assert row["ticket"] == "T-42"

    def test_get_thread_returns_messages_in_order(self, tmp_path):
        from claudarama.db import get_thread, store_message

        db_path = tmp_path / "office.db"
        init_db(db_path)

        store_message(db_path, sender="a", receiver="b", msg_type="START", body="first")
        store_message(db_path, sender="b", receiver="a", msg_type="DONE", body="second")

        thread = get_thread(db_path, participants=("a", "b"))
        assert len(thread) == 2
        assert thread[0]["body"] == "first"
        assert thread[1]["body"] == "second"

    def test_get_thread_is_empty_for_unknown_participants(self, tmp_path):
        from claudarama.db import get_thread

        db_path = tmp_path / "office.db"
        init_db(db_path)

        thread = get_thread(db_path, participants=("nobody", "also-nobody"))
        assert thread == []


# ---------------------------------------------------------------------------
# Slice 2: Brief builder appends thread history
# ---------------------------------------------------------------------------


class TestBriefWithThread:
    """Brief builder appends thread history when provided."""

    def test_build_brief_without_thread_works_as_before(self, tmp_path):
        from claudarama.brief import build_brief

        pack = tmp_path / ".claudarama"
        pack.mkdir()
        (pack / "company.md").write_text("# Acme Corp\n")
        (pack / "profiles").mkdir()

        brief = build_brief(pack_dir=pack, role="fullstack-engineer")
        assert "Acme Corp" in brief

    def test_build_brief_with_thread_appends_messages(self, tmp_path):
        from claudarama.brief import build_brief

        pack = tmp_path / ".claudarama"
        pack.mkdir()
        (pack / "company.md").write_text("# Acme Corp\n")
        (pack / "profiles").mkdir()
        (pack / "profiles" / "fullstack-engineer.md").write_text("You are a fullstack engineer.\n")

        thread = [
            {"sender": "bender", "receiver": "leela", "msg_type": "START", "body": "Here is your task"},
            {"sender": "leela", "receiver": "bender", "msg_type": "BLOCKED", "body": "Need more info"},
        ]

        brief = build_brief(pack_dir=pack, role="fullstack-engineer", thread=thread)
        assert "Here is your task" in brief
        assert "Need more info" in brief

    def test_build_brief_thread_section_labelled(self, tmp_path):
        from claudarama.brief import build_brief

        pack = tmp_path / ".claudarama"
        pack.mkdir()
        (pack / "company.md").write_text("# Acme Corp\n")
        (pack / "profiles").mkdir()

        thread = [{"sender": "a", "receiver": "b", "msg_type": "START", "body": "Hello"}]
        brief = build_brief(pack_dir=pack, role="engineer", thread=thread)
        assert "Message Thread" in brief or "thread" in brief.lower()


# ---------------------------------------------------------------------------
# Slice 3: `send` MCP tool
# ---------------------------------------------------------------------------


class TestSendMCPTool:
    """send tool: stores message, ends sender turn, queues receiver turn."""

    def test_send_tool_is_registered_on_server(self, tmp_path):
        from claudarama.daemon import create_mcp_server

        db_path = _setup_db(tmp_path)
        server = create_mcp_server(db_path=db_path)

        tools = asyncio.run(server.list_tools())
        tool_names = [t.name for t in tools]
        assert "send" in tool_names

    def test_send_tool_stores_message_in_db(self, tmp_path):
        """Calling the send tool function directly mutates the DB."""
        from claudarama.daemon import make_send_tool

        db_path = _setup_db(tmp_path)
        sender_turn_id = queue_turn(db_path, person_id="p1")
        send = make_send_tool(db_path)

        result = asyncio.run(
            send(
                sender_turn_id=sender_turn_id,
                sender_id="p1",
                receiver_id="p2",
                msg_type="DONE",
                body="Task complete",
            )
        )

        assert result.get("ok") is True

        with _connect(db_path) as conn:
            row = conn.execute(
                "SELECT sender, receiver, body FROM messages WHERE sender = 'p1'"
            ).fetchone()
        assert row is not None
        assert row["body"] == "Task complete"

    def test_send_tool_marks_sender_turn_done(self, tmp_path):
        """send marks the sender's active turn as done (clean end)."""
        from claudarama.daemon import make_send_tool

        db_path = _setup_db(tmp_path)
        sender_turn_id = queue_turn(db_path, person_id="p1")
        send = make_send_tool(db_path)

        asyncio.run(
            send(
                sender_turn_id=sender_turn_id,
                sender_id="p1",
                receiver_id="p2",
                msg_type="DONE",
                body="Task complete",
            )
        )

        with _connect(db_path) as conn:
            row = conn.execute(
                "SELECT status, ended_at FROM turns WHERE id = ?", (sender_turn_id,)
            ).fetchone()
        assert row["status"] == "done"
        assert row["ended_at"] is not None

    def test_send_tool_queues_new_turn_for_receiver(self, tmp_path):
        """send queues a fresh queued turn for the receiver."""
        from claudarama.daemon import make_send_tool

        db_path = _setup_db(tmp_path)
        sender_turn_id = queue_turn(db_path, person_id="p1")
        send = make_send_tool(db_path)

        result = asyncio.run(
            send(
                sender_turn_id=sender_turn_id,
                sender_id="p1",
                receiver_id="p2",
                msg_type="DONE",
                body="Task complete",
            )
        )

        with _connect(db_path) as conn:
            row = conn.execute(
                "SELECT status, thread_with FROM turns WHERE id = ?",
                (result["new_turn_id"],),
            ).fetchone()

        assert row["status"] == "queued"
        assert row["thread_with"] == "p1"

    def test_send_tool_receiver_brief_contains_thread(self, tmp_path):
        """Receiver's new turn is a reply turn: brief will contain thread history."""
        from claudarama.brief import build_brief
        from claudarama.daemon import make_send_tool
        from claudarama.db import get_thread

        db_path = _setup_db(tmp_path)
        sender_turn_id = queue_turn(db_path, person_id="p1")
        send = make_send_tool(db_path)

        result = asyncio.run(
            send(
                sender_turn_id=sender_turn_id,
                sender_id="p1",
                receiver_id="p2",
                msg_type="DONE",
                body="Here is the completed work",
            )
        )

        # The supervisor will use thread_with to fetch the live thread
        thread = get_thread(db_path, participants=("p2", "p1"))
        assert len(thread) == 1
        assert thread[0]["body"] == "Here is the completed work"

        # Verify the thread injects into the brief correctly
        pack = tmp_path / ".claudarama"
        pack.mkdir()
        (pack / "company.md").write_text("# Test Co\n")
        (pack / "profiles").mkdir()

        brief = build_brief(pack_dir=pack, role="cpo", thread=thread)
        assert "Here is the completed work" in brief
