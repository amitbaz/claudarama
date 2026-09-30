import json
import os
import subprocess
import sys


def open_ceo_session(
    host: str = "127.0.0.1",
    port: int = 8000,
    claude_binary: str = "claude",
) -> int:
    """Launch an interactive Claude session pointing to the daemon's MCP endpoint."""
    mcp_endpoint = f"http://{host}:{port}/mcp"
    mcp_config = {
        "mcpServers": {
            "claudarama": {
                "type": "http",
                "url": mcp_endpoint,
            }
        }
    }
    mcp_config_json = json.dumps(mcp_config)

    cmd = [
        claude_binary,
        "--mcp-config",
        mcp_config_json,
    ]

    try:
        proc = subprocess.run(cmd)
        return proc.returncode
    except FileNotFoundError:
        print(f"Error: '{claude_binary}' executable not found in PATH.", file=sys.stderr)
        return 1
