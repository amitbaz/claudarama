"""Turn identity tokens, the owner token and ``talk`` (issue #34)."""
import json
import sqlite3
from unittest.mock import patch

import pytest

from claudarama.daemon import authenticate, create_mcp_server, make_send_tool
from claudarama.db import (
    create_turn_token,
    end_session,
    get_owner_token,
    get_turn,
    has_open_session,
    init_db,
    mark_turn_done,
    mark_turn_running,
    queue_turn,
)
from claudarama.session import talk_to_person
from claudarama.supervisor import Supervisor


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "office.db"
    init_db(path)
    with sqlite3.connect(path) as conn:
        conn.executemany(
            "INSERT INTO people (id, name, role) VALUES (?, ?, ?)",
            [("p1", "Bender", "engineer"), ("p2", "Leela", "cpo")],
        )
    return path


def _running_turn(db, **kw):
    turn_id = queue_turn(db, "p1", **kw)
    mark_turn_running(db, turn_id)
    return turn_id


def test_turn_token_names_person_turn_and_ticket(db):
    turn_id = _running_turn(db, thread="ticket:T-1")
    who = authenticate(db, create_turn_token(db, turn_id))
    assert (who.person_id, who.turn_id, who.ticket) == ("p1", turn_id, "T-1")


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
    asyncio.run(make_send_tool(db)(who, "p2", "DONE", "hi", ticket="T-1"))
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT sender FROM messages").fetchone() == ("p1",)
    assert get_turn(db, turn_id)["status"] == "done"


def test_launch_carries_live_turn_token_in_mcp_url(db, tmp_path):
    turn_id = queue_turn(db, "p1")
    sup = Supervisor(db, tmp_path / ".claudarama", tmp_path, port=9001)
    launch = sup.build_launch(get_turn(db, turn_id))
    url = json.loads(launch.cmd[launch.cmd.index("--mcp-config") + 1])["mcpServers"]["claudarama"]["url"]
    assert url.startswith("http://127.0.0.1:9001/mcp/")
    mark_turn_running(db, turn_id)
    assert authenticate(db, url.rsplit("/", 1)[1]).turn_id == turn_id


def test_talk_records_open_session_until_exit(db, tmp_path):
    seen = {}

    def fake_run(cmd):
        url = json.loads(cmd[cmd.index("--mcp-config") + 1])["mcpServers"]["claudarama"]["url"]
        token = url.rsplit("/", 1)[1]
        seen["who"] = authenticate(db, token)
        seen["open"] = has_open_session(db, "p1")
        seen["token"] = token
        seen["cmd"] = cmd
        class R: returncode = 0
        return R()

    with patch("subprocess.run", side_effect=fake_run):
        assert talk_to_person("Bender", db_path=db, pack_dir=tmp_path) == 0
    assert seen["who"].person_id == "p1" and seen["open"]
    assert "--append-system-prompt" in seen["cmd"]
    assert not has_open_session(db, "p1")
    with pytest.raises(PermissionError):
        authenticate(db, seen["token"])


def test_talk_unknown_person(db, tmp_path):
    assert talk_to_person("Nobody", db_path=db, pack_dir=tmp_path) == 1


def test_mcp_url_token_reaches_tool_over_http(db):
    """End to end: the /mcp/<token> path decides who a tool call is."""
    import asyncio
    import socket
    import threading
    import time

    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = create_mcp_server(db_path=db, port=port)
    threading.Thread(target=server.run, kwargs={"transport": "streamable-http"}, daemon=True).start()
    time.sleep(1.5)  # ponytail: fixed wait for the server thread; poll the port if flaky

    async def whoami(token):
        async with streamablehttp_client(f"http://127.0.0.1:{port}/mcp/{token}") as (r, w, _):
            async with ClientSession(r, w) as client:
                await client.initialize()
                return await client.call_tool("whoami", {})

    ok = asyncio.run(asyncio.wait_for(whoami(get_owner_token(db)), 15))
    assert not ok.isError and '"owner"' in ok.content[0].text
    bad = asyncio.run(asyncio.wait_for(whoami("bogus"), 15))
    assert bad.isError and "token" in bad.content[0].text
