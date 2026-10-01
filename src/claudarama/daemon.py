import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from mcp.server.fastmcp import Context, FastMCP

from claudarama.mirror import Gh, run_gh, sync

from claudarama.db import (
    Identity,
    get_office_db_path,
    grant_mandate,
    init_db,
    mark_turn_done,
    queue_turn,
    register_ticket,
    resolve_token,
    store_message,
    submit_diagnosis,
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

        if msg_type in ("DONE", "BLOCKED", "QUESTION"):
            from claudarama.supervisor import load_org_settings
            settings = load_org_settings(db_path.parent)
            new_turn_id = queue_turn(
                db_path, 
                person_id=receiver_id, 
                thread=thread, 
                delay_minutes=settings.batch_window_minutes
            )
            return {"ok": True, "new_turn_id": new_turn_id}
            
        return {"ok": True, "new_turn_id": None}

    return send


def create_mcp_server(
    db_path: Path | None = None, host: str = "127.0.0.1", port: int = 8000, gh: Gh | None = None
) -> FastMCP:
    """Create and configure the Claudarama FastMCP server. With *gh*, grants and tickets mirror to GitHub."""
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
    def pin(note: str, ticket: str, ctx: Context) -> dict:
        """Store a working note (max 500 chars) for a ticket."""
        if len(note) > 500:
            raise ValueError("working note over 500 characters")
        identity = authenticate(db_path, _token_of(ctx))
        person_id = identity.person_id or "ceo"
        from claudarama.db import set_working_note
        set_working_note(db_path, person_id, ticket, note)
        return {"ok": True}

    @server.tool()
    def grant(mandate: str, ctx: Context) -> dict:
        """Grant a mandate. Owner token only."""
        authenticate(db_path, _token_of(ctx), owner_only=True)
        grant_mandate(db_path, mandate)
        if gh:
            sync(db_path, gh)
        return {"ok": True, "mandate": mandate}

    @server.tool(name="submit_diagnosis")
    def submit_diagnosis_tool(mandate: str, diagnosis_path: str, ctx: Context) -> dict:
        """Submit a Diagnosis: the mandate moves to PLANNING and pauses for the CEO."""
        authenticate(db_path, _token_of(ctx))
        submit_diagnosis(db_path, mandate, diagnosis_path)
        return {"ok": True, "mandate": mandate, "status": "PLANNING", "blocked_on_ceo": True}

    @server.tool()
    def ticket_ready(ticket: str, mandate: str, ctx: Context, hard: bool = False) -> dict:
        """Register a ticket under a granted mandate; refused if the mandate is not granted."""
        authenticate(db_path, _token_of(ctx))
        register_ticket(db_path, ticket, mandate, hard)
        if gh:
            sync(db_path, gh)
        return {"ok": True, "ticket": ticket, "mandate": mandate, "hard": hard}

    @server.tool()
    def whoami(ctx: Context) -> dict:
        """Who the token in the MCP URL speaks for."""
        return asdict(authenticate(db_path, _token_of(ctx)))

    @server.tool()
    def record_ship_check(
        pull_request: int, head_commit: str, verdict: str, diagnosis_path: str, command: str, ctx: Context
    ) -> dict:
        """Log a Ship-check verdict (SHIP or FAIL) for a PR's head commit, with the Diagnosis path
        and the verification command you ran. The reviewer is taken from your token."""
        from claudarama.db import record_verdict
        identity = authenticate(db_path, _token_of(ctx))
        reviewer_id = identity.person_id or "ceo"
        record_verdict(db_path, pull_request, head_commit, reviewer_id, verdict, diagnosis_path, command)
        return {"ok": True, "pull_request": pull_request, "head_commit": head_commit, "verdict": verdict}

    @server.tool()
    def checkpoint(content: str, ctx: Context) -> dict:
        """Save a checkpoint before compaction. Only works for turns running a ticket thread."""
        from claudarama.db import save_checkpoint
        identity = authenticate(db_path, _token_of(ctx))
        if not identity.ticket:
            raise ValueError("cannot save checkpoint without a ticket thread")
        save_checkpoint(db_path, identity.person_id or "ceo", identity.ticket, content)
        return {"ok": True}

    return server


def run_daemon(
    host: str = "127.0.0.1",
    port: int = 8000,
    project_name: str | None = None,
    transport: str = "streamable-http",
) -> None:
    """Initialize DB and run the FastMCP daemon."""
    db_path = get_office_db_path(project_name)
    server = create_mcp_server(db_path=db_path, host=host, port=port, gh=run_gh)

    def reconcile() -> None:  # catches hand-moved issues
        while True:
            time.sleep(60)
            sync(db_path, run_gh)

    threading.Thread(target=reconcile, daemon=True).start()
    server.run(transport=transport)
