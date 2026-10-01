"""The office server as one process per caller (ADR-0003, issue #83).

Each test starts the server the way Claude Code would: from the ``--mcp-config``
that ``claudarama open`` or a turn launch hands to ``claude``, over stdio.
"""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from claudarama.db import get_owner_token, get_turn, init_db, mark_turn_done, mark_turn_running, queue_turn
from claudarama.session import DB_ENV, TOKEN_ENV, mcp_config, open_ceo_session
from claudarama.supervisor import Supervisor


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "office.db"
    init_db(path)
    return path


@pytest.fixture
def office(tmp_path):
    """``office(config)``: an MCP client on a server process started from *config*."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("gh", "claude"):  # the server never reaches the real GitHub, nor launches a real turn
        (fake_bin / name).write_text("#!/bin/sh\nexit 1\n")
        (fake_bin / name).chmod(0o755)

    @asynccontextmanager
    async def office(config: str):
        spec = json.loads(config)["mcpServers"]["claudarama"]
        env = {**spec["env"], "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"}
        params = StdioServerParameters(command=spec["command"], args=spec["args"], env=env, cwd=tmp_path)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                yield client

    return office


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, 30))


@pytest.fixture
def serve(office):
    """``serve(config, script)``: start the office server from *config*, run ``script(client)``."""

    def serve(config: str, script):
        async def run():
            async with office(config) as client:
                return await script(client)

        return _run(run())

    return serve


def _turn_config(db, tmp_path, **turn) -> tuple[str, str]:
    """A running turn and the ``--mcp-config`` its ``claude`` was launched with."""
    turn_id = queue_turn(db, "fullstack-engineer", **turn)
    launch = Supervisor(db, tmp_path / ".claudarama", tmp_path).build_launch(get_turn(db, turn_id))
    mark_turn_running(db, turn_id)
    return turn_id, launch.cmd[launch.cmd.index("--mcp-config") + 1]


def test_open_attaches_the_office_server_with_nothing_started_first(tmp_path, serve):
    with patch("subprocess.run") as claude:
        claude.return_value.returncode = 0
        assert open_ceo_session(db_path=tmp_path / "office.db") == 0
    cmd = claude.call_args.args[0]

    who = serve(cmd[cmd.index("--mcp-config") + 1], lambda c: c.call_tool("whoami", {}))

    assert not who.isError and json.loads(who.content[0].text)["kind"] == "owner"


def test_a_turns_server_speaks_for_that_turn_until_the_turn_ends(db, tmp_path, serve):
    turn_id, config = _turn_config(db, tmp_path, thread="ticket:T-1")

    async def script(client):
        during = await client.call_tool("whoami", {})
        mark_turn_done(db, turn_id)
        return during, await client.call_tool("whoami", {})

    during, after = serve(config, script)

    who = json.loads(during.content[0].text)
    assert (who["kind"], who["person_id"], who["turn_id"], who["ticket"]) == ("turn", "fullstack-engineer", turn_id, "T-1")
    assert after.isError and "expired" in after.content[0].text


def test_a_turn_does_not_inherit_its_launchers_token(db, tmp_path, monkeypatch):
    """A server process holds its token in its environment; a turn launched from it gets only its own."""
    monkeypatch.setenv(TOKEN_ENV, get_owner_token(db))
    turn_id = queue_turn(db, "fullstack-engineer")

    launch = Supervisor(db, tmp_path / ".claudarama", tmp_path).build_launch(get_turn(db, turn_id))

    assert TOKEN_ENV not in launch.env
    assert get_owner_token(db) not in json.dumps([launch.cmd, launch.env])


def test_only_the_owners_server_may_grant_a_mandate(db, tmp_path, serve):
    _, turn_config = _turn_config(db, tmp_path)

    async def as_turn(client):
        return (
            await client.call_tool("grant", {"mandate": "M1"}),
            await client.call_tool("ticket_ready", {"ticket": "T-1", "mandate": "M1"}),
        )

    refused, ungranted = serve(turn_config, as_turn)
    assert refused.isError and "owner" in refused.content[0].text
    assert ungranted.isError and "not granted" in ungranted.content[0].text

    granted = serve(mcp_config(db, get_owner_token(db)), lambda c: c.call_tool("grant", {"mandate": "M1"}))
    assert not granted.isError
    # The owner's server opened the office, which took back the turn above as one left running.
    _, turn_config = _turn_config(db, tmp_path)
    assert not serve(turn_config, as_turn)[1].isError  # a turn's server sees the owner's grant


def test_two_offices_are_open_at_once_with_no_port_between_them(tmp_path, office):
    dbs = [tmp_path / name / "office.db" for name in ("one", "two")]
    for db in dbs:
        init_db(db)
    configs = [mcp_config(db, get_owner_token(db)) for db in dbs]

    async def both():
        async with office(configs[0]) as one, office(configs[1]) as two:
            return [json.loads((await c.call_tool("health", {})).content[0].text)["db"] for c in (one, two)]

    assert _run(both()) == [str(db) for db in dbs]
    for config in configs:  # a command to start, nothing to listen on
        assert set(json.loads(config)["mcpServers"]["claudarama"]) == {"command", "args", "env"}


@pytest.mark.parametrize("env", [{}, {TOKEN_ENV: ""}, {TOKEN_ENV: "not-a-token"}])
def test_a_server_without_a_live_token_refuses_every_call(db, serve, env):
    spec = json.loads(mcp_config(db, "replaced below"))
    spec["mcpServers"]["claudarama"]["env"] = {DB_ENV: str(db), **env}

    async def script(client):
        return [await client.call_tool(name, args) for name, args in (
            ("whoami", {}), ("health", {}), ("grant", {"mandate": "M1"}),
            ("ticket_ready", {"ticket": "T-1", "mandate": "M1"}),
        )]

    for result in serve(json.dumps(spec), script):
        assert result.isError and "token" in result.content[0].text
