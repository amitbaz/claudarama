"""Tests for office server creation."""
from mcp.server.fastmcp import FastMCP
from claudarama.daemon import create_mcp_server
from claudarama.db import init_db


def test_create_mcp_server(tmp_path):
    db_path = tmp_path / "office.db"
    init_db(db_path)
    server = create_mcp_server(db_path=db_path)
    assert isinstance(server, FastMCP)
    assert server.name == "claudarama"
