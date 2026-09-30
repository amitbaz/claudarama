"""Tests for CEO session launcher (claudarama open)."""
import json
from unittest.mock import patch

from claudarama.session import open_ceo_session


def test_open_ceo_session_command():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0

        ret = open_ceo_session(host="127.0.0.1", port=8000, claude_binary="claude")
        assert ret == 0

        assert mock_run.called
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert cmd[0] == "claude"
        assert cmd[1] == "--mcp-config"

        config = json.loads(cmd[2])
        assert "mcpServers" in config
        assert "claudarama" in config["mcpServers"]
        assert config["mcpServers"]["claudarama"]["url"] == "http://127.0.0.1:8000/mcp"
        assert config["mcpServers"]["claudarama"]["type"] == "http"


def test_open_ceo_session_claude_not_found():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        ret = open_ceo_session(host="127.0.0.1", port=8000, claude_binary="nonexistent-claude")
        assert ret == 1
