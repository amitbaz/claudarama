"""Tests for CEO session launcher (claudarama open). The attached server is driven in test_office_server."""
from unittest.mock import patch

from claudarama.session import open_ceo_session


def test_open_ceo_session_command(tmp_path):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0

        assert open_ceo_session(claude_binary="claude", db_path=tmp_path / "office.db") == 0

        cmd = mock_run.call_args.args[0]
        assert cmd[:2] == ["claude", "--mcp-config"]


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
        ret = open_ceo_session(claude_binary="nonexistent-claude", db_path=tmp_path / "office.db")
        assert ret == 1
