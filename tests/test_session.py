"""Tests for CEO session launcher (claudarama open)."""
import json
from unittest.mock import patch

from claudarama.db import get_owner_token
from claudarama.session import open_ceo_session


def test_open_ceo_session_command(tmp_path):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0

        ret = open_ceo_session(host="127.0.0.1", port=8000, claude_binary="claude", db_path=tmp_path / "office.db")
        assert ret == 0

        assert mock_run.called
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert cmd[0] == "claude"
        assert cmd[1] == "--mcp-config"

        config = json.loads(cmd[2])
        assert "mcpServers" in config
        assert "claudarama" in config["mcpServers"]
        owner = get_owner_token(tmp_path / "office.db")
        assert config["mcpServers"]["claudarama"]["url"] == f"http://127.0.0.1:8000/mcp/{owner}"
        assert config["mcpServers"]["claudarama"]["type"] == "http"


def test_open_loads_the_assistants_role_file_into_the_ceos_session(tmp_path):
    pack = tmp_path / ".claudarama"
    pack.mkdir()
    (pack / "company.md").write_text("CHARTER-TEXT\n")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        open_ceo_session(db_path=tmp_path / "office.db", pack_dir=pack)

    cmd = mock_run.call_args.args[0]
    brief = cmd[cmd.index("--append-system-prompt") + 1]
    assert "CHARTER-TEXT" in brief
    assert "You are the assistant (Nibbler)." in brief
    assert "**The setup interview**" in brief


def test_open_ceo_session_claude_not_found(tmp_path):
    with patch("subprocess.run", side_effect=FileNotFoundError):
        ret = open_ceo_session(host="127.0.0.1", port=8000, claude_binary="nonexistent-claude", db_path=tmp_path / "office.db")
        assert ret == 1
