import json
import subprocess
import sys
from pathlib import Path

from claudarama.brief import build_brief
from claudarama.db import (
    end_session,
    get_office_db_path,
    get_owner_token,
    get_person_by_name,
    init_db,
    start_session,
)


def _run_claude(cmd: list[str], claude_binary: str) -> int:
    try:
        return subprocess.run(cmd).returncode
    except FileNotFoundError:
        print(f"Error: '{claude_binary}' executable not found in PATH.", file=sys.stderr)
        return 1


def mcp_config(host: str, port: int, token: str) -> str:
    url = f"http://{host}:{port}/mcp/{token}"
    return json.dumps({"mcpServers": {"claudarama": {"type": "http", "url": url}}})


def open_ceo_session(
    host: str = "127.0.0.1",
    port: int = 8000,
    claude_binary: str = "claude",
    db_path: Path | None = None,
) -> int:
    """Launch an interactive Claude session holding the owner token."""
    db_path = db_path or get_office_db_path()
    init_db(db_path)
    config = mcp_config(host, port, get_owner_token(db_path))
    return _run_claude([claude_binary, "--mcp-config", config], claude_binary)


def talk_to_person(
    name: str,
    host: str = "127.0.0.1",
    port: int = 8000,
    claude_binary: str = "claude",
    db_path: Path | None = None,
    pack_dir: Path | None = None,
) -> int:
    """Interactive session with *name*: their token and brief; recorded open until it exits."""
    db_path = db_path or get_office_db_path()
    init_db(db_path)
    person = get_person_by_name(db_path, name)
    if person is None:
        print(f"Error: no person named '{name}'.", file=sys.stderr)
        return 1
    brief = build_brief(pack_dir or Path.cwd() / ".claudarama", person["role"])
    token = start_session(db_path, person["id"])
    cmd = [
        claude_binary,
        "--mcp-config", mcp_config(host, port, token),
        "--append-system-prompt", brief,
    ]
    try:
        return _run_claude(cmd, claude_binary)
    finally:
        end_session(db_path, token)
