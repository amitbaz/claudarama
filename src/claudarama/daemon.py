from pathlib import Path
from typing import Callable

from mcp.server.fastmcp import FastMCP

from claudarama.db import (
    get_office_db_path,
    init_db,
    mark_turn_done,
    queue_turn,
    store_message,
    thread_key,
)


def make_send_tool(db_path: Path) -> Callable:
    """Return the async ``send`` function bound to *db_path*.

    Factored out so tests can call the business logic directly without
    wiring up an HTTP server.
    """

    async def send(
        sender_turn_id: str,
        sender_id: str,
        receiver_id: str,
        msg_type: str,
        body: str,
        ticket: str | None = None,
        topic: str | None = None,
    ) -> dict:
        """Send a message from sender to receiver and end the sender's turn.

        The message belongs to the thread of its *ticket*, or of its *topic*
        when there is no ticket; one of the two is required.

        Steps:
        1. Stores the message in the DB.
        2. Marks the sender's active turn as done (clean end).
        3. Queues a fresh turn for the receiver with a ``thread`` pointer
           so the supervisor will inject only that thread into its brief.

        Returns ``{"ok": True, "new_turn_id": "<uuid>"}`` on success.
        """
        thread = thread_key(ticket, topic)  # refuse before touching the DB
        store_message(
            db_path,
            sender=sender_id,
            receiver=receiver_id,
            msg_type=msg_type,
            body=body,
            ticket=ticket,
            topic=topic,
        )
        mark_turn_done(db_path, sender_turn_id)
        new_turn_id = queue_turn(db_path, person_id=receiver_id, thread=thread)
        return {"ok": True, "new_turn_id": new_turn_id}

    return send


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

    # Register the send tool using the factory so both the server and tests
    # share the same implementation.
    server.tool()(make_send_tool(db_path))

    return server


def run_daemon(
    host: str = "127.0.0.1",
    port: int = 8000,
    project_name: str | None = None,
    transport: str = "streamable-http",
) -> None:
    """Initialize DB and run the FastMCP daemon."""
    db_path = get_office_db_path(project_name)
    server = create_mcp_server(db_path=db_path, host=host, port=port)
    server.run(transport=transport)
