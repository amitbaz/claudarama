from dataclasses import asdict
from pathlib import Path
from typing import Callable

from mcp.server.fastmcp import Context, FastMCP

from claudarama.db import (
    Identity,
    get_office_db_path,
    init_db,
    mark_turn_done,
    queue_turn,
    resolve_token,
    store_message,
    thread_key,
)


def authenticate(db_path: Path, token: str | None, owner_only: bool = False) -> Identity:
    """Identity behind *token*; raises PermissionError with a reason when refused."""
    identity = resolve_token(db_path, token)
    if identity is None:
        raise PermissionError("missing, unknown or expired token")
    if owner_only and not identity.is_owner:
        raise PermissionError("owner-only tool: needs the owner token")
    return identity


def _token_of(ctx: Context) -> str | None:
    """The token in the MCP URL path ``/mcp/<token>``."""
    return ctx.request_context.request.path_params.get("token")


def make_send_tool(db_path: Path) -> Callable:
    """Return the async ``send`` function bound to *db_path*.

    Factored out so tests can call the business logic directly without
    wiring up an HTTP server.
    """

    async def send(
        identity: Identity,
        receiver_id: str,
        msg_type: str,
        body: str,
        ticket: str | None = None,
        topic: str | None = None,
    ) -> dict:
        """Send a message from the caller to receiver and end the caller's turn.

        The sender is the caller's identity, never an argument. The owner
        sends as ``ceo``; a ``talk`` session has no turn to end.

        The message belongs to the thread of its *ticket*, or of its *topic*
        when there is no ticket; one of the two is required.

        Steps:
        1. Stores the message in the DB.
        2. Marks the caller's turn as done (clean end), if it is a turn.
        3. Queues a fresh turn for the receiver with a ``thread`` pointer
           so the supervisor will inject only that thread into its brief.

        Returns ``{"ok": True, "new_turn_id": "<uuid>"}`` on success.
        """
        thread = thread_key(ticket, topic)  # refuse before touching the DB
        store_message(
            db_path,
            sender=identity.person_id or "ceo",
            receiver=receiver_id,
            msg_type=msg_type,
            body=body,
            ticket=ticket,
            topic=topic,
        )
        if identity.turn_id:
            mark_turn_done(db_path, identity.turn_id)
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
        streamable_http_path="/mcp/{token}",
    )

    @server.tool()
    def health(ctx: Context) -> dict[str, str]:
        """Health check endpoint for claudarama daemon."""
        authenticate(db_path, _token_of(ctx))
        return {"status": "ok", "db": str(db_path)}

    send = make_send_tool(db_path)

    @server.tool(name="send")
    async def send_tool(
        receiver_id: str,
        msg_type: str,
        body: str,
        ctx: Context,
        ticket: str | None = None,
        topic: str | None = None,
    ) -> dict:
        """Send a message and end your turn. The sender is taken from your token."""
        identity = authenticate(db_path, _token_of(ctx))
        return await send(identity, receiver_id, msg_type, body, ticket, topic)

    @server.tool()
    def whoami(ctx: Context) -> dict:
        """Who the token in the MCP URL speaks for."""
        return asdict(authenticate(db_path, _token_of(ctx)))

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
