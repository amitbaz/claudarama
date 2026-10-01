"""Turn identity tokens and the owner token (issue #34). test_office_server drives them through a server process."""
import sqlite3

import pytest

from claudarama.daemon import authenticate, make_send_tool
from claudarama.db import (
    create_turn_token,
    get_owner_token,
    get_turn,
    init_db,
    mark_turn_done,
    mark_turn_running,
    queue_turn,
)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "office.db"
    init_db(path)
    return path


def _running_turn(db, **kw):
    turn_id = queue_turn(db, "fullstack-engineer", **kw)
    mark_turn_running(db, turn_id)
    return turn_id


def test_turn_token_names_person_turn_and_ticket(db):
    turn_id = _running_turn(db, thread="ticket:T-1")
    who = authenticate(db, create_turn_token(db, turn_id))
    assert (who.person_id, who.turn_id, who.ticket) == ("fullstack-engineer", turn_id, "T-1")


@pytest.mark.parametrize("token", [None, "", "nope"])
def test_missing_or_unknown_token_refused(db, token):
    with pytest.raises(PermissionError):
        authenticate(db, token)


def test_token_dies_when_turn_ends(db):
    turn_id = _running_turn(db)
    token = create_turn_token(db, turn_id)
    mark_turn_done(db, turn_id)
    with pytest.raises(PermissionError, match="expired"):
        authenticate(db, token)


def test_owner_only_refuses_turn_token_with_reason(db):
    turn_token = create_turn_token(db, _running_turn(db))
    with pytest.raises(PermissionError, match="owner"):
        authenticate(db, turn_token, owner_only=True)
    assert authenticate(db, get_owner_token(db), owner_only=True).is_owner


def test_owner_token_is_stable(db):
    assert get_owner_token(db) == get_owner_token(db)


def test_send_attributes_sender_from_identity(db):
    import asyncio

    turn_id = _running_turn(db)
    who = authenticate(db, create_turn_token(db, turn_id))
    asyncio.run(make_send_tool(db)(who, "pm", "DONE", "hi", ticket="T-1"))
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT sender FROM messages").fetchone() == ("fullstack-engineer",)
    assert get_turn(db, turn_id)["status"] == "done"
