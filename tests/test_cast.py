"""The fixed cast (issue #86): ten Persons from the first day, addressed by Role."""
import asyncio
import sqlite3

import pytest

from claudarama.brief import build_brief
from claudarama.daemon import make_send_tool
from claudarama.db import (
    Identity, get_office_db_path, get_person_by_role, get_thread, get_turn, init_db,
    mark_turn_running, queue_turn, save_turn_usage,
)
from claudarama.status import print_status

# Spec #79, "The cast and role files".
SPEC_CAST = {
    "assistant": "Nibbler",
    "pm": "Hermes",
    "engineering-lead": "Kif",
    "fullstack-engineer": "Bender",
    "frontend-engineer": "Fry",
    "database-architect": "Scruffy",
    "designer": "Zoidberg",
    "prompt-engineer": "Cubert",
    "eval-engineer": "Morbo",
    "researcher": "Amy",
}


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "office.db"
    init_db(path)
    return path


def test_a_new_office_holds_the_ten_persons_one_per_role(db):
    assert {role: get_person_by_role(db, role)["name"] for role in SPEC_CAST} == SPEC_CAST
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM people").fetchone()[0] == 10


def _people_columns(path):
    with sqlite3.connect(path) as conn:
        return {r[1] for r in conn.execute("PRAGMA table_info(people)")}


def test_a_person_has_an_identifier_a_name_and_a_role_and_nothing_else(db):
    assert set(get_person_by_role(db, "designer")) == {"id", "name", "role"}
    assert not _people_columns(db) & {"level", "manager_id"}


def test_level_and_manager_are_dropped_from_an_office_created_before_the_cast(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE people (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, role TEXT NOT NULL, "
            "level INTEGER NOT NULL DEFAULT 1, manager_id TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    init_db(path)
    assert not _people_columns(path) & {"level", "manager_id"}
    assert get_person_by_role(path, "researcher")["name"] == "Amy"


def test_status_shows_a_person_as_role_then_name(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    db = get_office_db_path("shop")
    init_db(db)
    save_turn_usage(db, queue_turn(db, "designer"), {"input_tokens": 100, "output_tokens": 50, "cost": 0.05})
    assert print_status("shop") == 0
    assert "designer (Zoidberg): 100 in, 50 out, $0.05" in capsys.readouterr().out


def test_a_briefs_thread_shows_each_person_as_role_then_name(tmp_path):
    thread = [
        {"sender": "ceo", "receiver": "pm", "msg_type": "QUESTION", "body": "when?"},
        {"sender": "pm", "receiver": "designer", "msg_type": "QUESTION", "body": "mockups?"},
    ]
    brief = build_brief(tmp_path, "designer", thread=thread)
    assert "**ceo → pm (Hermes)** [QUESTION]: when?" in brief
    assert "**pm (Hermes) → designer (Zoidberg)** [QUESTION]: mockups?" in brief


def _running_turn(db, role):
    turn_id = queue_turn(db, role, kind="ritual")
    mark_turn_running(db, turn_id)
    return turn_id


def _send(db, sender, receiver, **thread):
    identity = Identity("turn", sender, _running_turn(db, sender))
    return identity, asyncio.run(make_send_tool(db)(identity, receiver, "QUESTION", "hello", **thread))


def test_a_message_to_a_role_wakes_that_roles_person(db):
    _, sent = _send(db, "pm", "designer", ticket="T-1")
    assert get_turn(db, sent["new_turn_id"])["role"] == "designer"


def test_a_message_to_an_unknown_role_is_refused_with_a_reason(db):
    with pytest.raises(ValueError, match=r"unknown Role 'cto'.*designer \(Zoidberg\)") as refusal:
        _send(db, "pm", "cto", ticket="T-1")
    assert "Zoidberg (designer)" not in str(refusal.value)
    assert get_thread(db, "ticket:T-1") == []  # nothing accepted, nothing silently undelivered
    with sqlite3.connect(db) as conn:  # and the sender's turn is not ended by a refused message
        assert conn.execute("SELECT status FROM turns").fetchall() == [("running",)]
