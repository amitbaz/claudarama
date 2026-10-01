import os
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from mcp.server.fastmcp import FastMCP

from claudarama.mirror import Gh, run_gh, sync
from claudarama.scaffold import PACK_DIR_NAME
from claudarama.session import DB_ENV, TOKEN_ENV
from claudarama.supervisor import Supervisor

from claudarama.db import (
    CAST,
    Identity,
    get_office_db_path,
    get_person_by_role,
    get_project_root,
    grant_mandate,
    init_db,
    mark_turn_done,
    queue_turn,
    register_ticket,
    resolve_token,
    shown,
    store_message,
    submit_diagnosis,
    submit_epic,
    submit_lessons,
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


def make_send_tool(db_path: Path) -> Callable:
    """Return the async ``send`` function bound to *db_path*.

    Factored out so tests can call the business logic directly without
    starting a server process.
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

        The receiver is addressed by Role (*receiver_id*); an unknown Role is refused.

        The sender is the caller's identity, never an argument. The owner
        sends as ``ceo`` and has no turn to end.

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
        receiver = get_person_by_role(db_path, receiver_id)
        if receiver is None:
            raise ValueError(
                f"unknown Role {receiver_id!r}; the Roles are: {', '.join(map(shown, CAST))}"
            )
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
                person_id=receiver["id"],
                thread=thread, 
                delay_minutes=settings.batch_window_minutes
            )
            return {"ok": True, "new_turn_id": new_turn_id}
            
        return {"ok": True, "new_turn_id": None}

    return send


def create_mcp_server(
    db_path: Path | None = None, token: str | None = None, gh: Gh | None = None
) -> FastMCP:
    """The office server for one caller: every tool call is made as the holder of *token*.

    With *gh*, grants and tickets mirror to GitHub.
    """
    if db_path is None:
        db_path = get_office_db_path()
    init_db(db_path)

    server = FastMCP("claudarama")

    @server.tool()
    def health() -> dict[str, str]:
        """Health check for the office server."""
        authenticate(db_path, token)
        return {"status": "ok", "db": str(db_path)}

    send = make_send_tool(db_path)

    @server.tool(name="send")
    async def send_tool(
        receiver_id: str,
        msg_type: str,
        body: str,
        ticket: str | None = None,
        topic: str | None = None,
    ) -> dict:
        """Send a message to a Role (receiver_id) and end your turn. The sender is taken from your token."""
        identity = authenticate(db_path, token)
        return await send(identity, receiver_id, msg_type, body, ticket, topic)

    @server.tool()
    def pin(note: str, ticket: str) -> dict:
        """Store a working note (max 500 chars) for a ticket."""
        if len(note) > 500:
            raise ValueError("working note over 500 characters")
        identity = authenticate(db_path, token)
        person_id = identity.person_id or "ceo"
        from claudarama.db import set_working_note
        set_working_note(db_path, person_id, ticket, note)
        return {"ok": True}

    @server.tool()
    def grant(mandate: str) -> dict:
        """Grant a mandate. Owner token only."""
        authenticate(db_path, token, owner_only=True)
        grant_mandate(db_path, mandate)
        if gh:
            sync(db_path, gh)
        return {"ok": True, "mandate": mandate}

    @server.tool(name="submit_diagnosis")
    def submit_diagnosis_tool(mandate: str, diagnosis_path: str) -> dict:
        """Submit a Diagnosis: the mandate moves to PLANNING and pauses for the CEO."""
        authenticate(db_path, token)
        submit_diagnosis(db_path, mandate, diagnosis_path)
        return {"ok": True, "mandate": mandate, "status": "PLANNING", "blocked_on_ceo": True}

    @server.tool(name="submit_epic")
    def submit_epic_tool(mandate: str, tickets: list[str]) -> dict:
        """Submit an Epic, the drafted tickets of a PLANNING mandate: it moves to EXECUTING and pauses for the CEO."""
        authenticate(db_path, token)
        submit_epic(db_path, mandate, tickets)
        return {"ok": True, "mandate": mandate, "status": "EXECUTING", "blocked_on_ceo": True, "tickets": tickets}

    @server.tool(name="submit_lessons")
    def submit_lessons_tool(mandate: str, lesson_path: str) -> dict:
        """Submit the Lessons of a LEARNING mandate: it moves to CLOSED and pauses for the CEO."""
        authenticate(db_path, token)
        submit_lessons(db_path, mandate, lesson_path)
        return {"ok": True, "mandate": mandate, "status": "CLOSED", "blocked_on_ceo": True}

    @server.tool()
    def ticket_ready(ticket: str, mandate: str, hard: bool = False) -> dict:
        """Register a ticket under a granted mandate; refused if the mandate is not granted."""
        authenticate(db_path, token)
        register_ticket(db_path, ticket, mandate, hard)
        if gh:
            sync(db_path, gh)
        return {"ok": True, "ticket": ticket, "mandate": mandate, "hard": hard}

    @server.tool()
    def whoami() -> dict:
        """Who this server's token speaks for."""
        return asdict(authenticate(db_path, token))

    @server.tool()
    def record_ship_check(
        pull_request: int, head_commit: str, verdict: str, diagnosis_path: str, command: str
    ) -> dict:
        """Log a Ship-check verdict (SHIP or FAIL) for a PR's head commit, with the Diagnosis path
        and the verification command you ran. The reviewer is taken from your token; only the
        engineering-lead's verdict is accepted."""
        from claudarama.db import record_verdict
        identity = authenticate(db_path, token)
        reviewer_id = identity.person_id or "ceo"
        record_verdict(db_path, pull_request, head_commit, reviewer_id, verdict, diagnosis_path, command)
        return {"ok": True, "pull_request": pull_request, "head_commit": head_commit, "verdict": verdict}

    @server.tool()
    def checkpoint(content: str) -> dict:
        """Save a checkpoint before compaction. Only works for turns running a ticket thread."""
        from claudarama.db import save_checkpoint
        identity = authenticate(db_path, token)
        if not identity.ticket:
            raise ValueError("cannot save checkpoint without a ticket thread")
        save_checkpoint(db_path, identity.person_id or "ceo", identity.ticket, content)
        return {"ok": True}

    return server


def main() -> None:
    """Run the office server for one caller over stdio. Claude Code starts this process."""
    db = os.environ.get(DB_ENV)
    db_path = Path(db) if db else get_office_db_path()
    token = os.environ.get(TOKEN_ENV)
    server = create_mcp_server(db_path=db_path, token=token, gh=run_gh)

    def reconcile() -> None:  # catches hand-moved issues
        while True:
            time.sleep(60)
            sync(db_path, run_gh)

    identity = resolve_token(db_path, token)
    if not (identity and identity.is_owner):  # a turn's server neither reconciles nor runs turns
        server.run()
        return
    threading.Thread(target=reconcile, daemon=True).start()
    # The CEO's Session runs the office: transcripts stay with the office's state, outside the project.
    office = Supervisor(db_path, get_project_root() / PACK_DIR_NAME, db_path.parent / "turns")
    threading.Thread(target=office.run, daemon=True).start()
    try:
        server.run()
    finally:  # the Session closed
        office.close()


if __name__ == "__main__":
    main()
