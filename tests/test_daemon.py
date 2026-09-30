"""Tests for FastMCP daemon creation and endpoints."""
import pytest
from unittest.mock import patch
from mcp.server.fastmcp import FastMCP
from claudarama.daemon import create_mcp_server, run_daemon
from claudarama.db import init_db


def test_create_mcp_server(tmp_path):
    db_path = tmp_path / "office.db"
    init_db(db_path)
    server = create_mcp_server(db_path=db_path)
    assert isinstance(server, FastMCP)
    assert server.name == "claudarama"


def test_run_daemon_initializes_db_and_runs_server(tmp_path):
    with patch("claudarama.daemon.get_office_db_path") as mock_db_path:
        db_path = tmp_path / "office.db"
        mock_db_path.return_value = db_path

        with patch.object(FastMCP, "run") as mock_run:
            run_daemon(host="127.0.0.1", port=8000, project_name="test-project")
            assert db_path.exists()
            mock_run.assert_called_once_with(transport="streamable-http")
