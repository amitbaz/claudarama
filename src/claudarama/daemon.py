from pathlib import Path
from mcp.server.fastmcp import FastMCP
from claudarama.db import get_office_db_path, init_db


def create_mcp_server(db_path: Path | None = None, host: str = "127.0.0.1", port: int = 8000) -> FastMCP:
    """Create and configure the Claudarama FastMCP server."""
    if db_path is None:
        db_path = get_office_db_path()
    init_db(db_path)

    server = FastMCP(
        "claudarama",
        host=host,
        port=port,
        streamable_http_path="/mcp",
    )

    @server.tool()
    def health() -> dict[str, str]:
        """Health check endpoint for claudarama daemon."""
        return {"status": "ok", "db": str(db_path)}

    return server


def run_daemon(
    host: str = "127.0.0.1",
    port: int = 8000,
    project_name: str | None = None,
    transport: str = "streamable-http",
) -> None:
    """Initialize DB and run the FastMCP daemon."""
    db_path = get_office_db_path(project_name)
    init_db(db_path)
    server = create_mcp_server(db_path=db_path, host=host, port=port)
    server.run(transport=transport)
