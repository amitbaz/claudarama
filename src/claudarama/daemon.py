import os
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from mcp.server.fastmcp import FastMCP

from claudarama.documents import DIAGNOSES, RETROS, committed, document_path, missing_sections, open_pull_request
from claudarama.mirror import Gh, run_gh, sync
from claudarama.scaffold import PACK_DIR_NAME
from claudarama.session import DB_ENV, TOKEN_ENV, advance_to_learning, follow_github, open_gates, watch_gates
from claudarama.supervisor import Supervisor, notify_ceo
from claudarama.worktrees import remove_finished_worktrees

from claudarama.db import (
    CAST,
    Identity,
    adopt_lesson,
    adopted_lessons,
    get_office_db_path,
    get_person_by_role,
    get_project_root,
    grant_mandate,
    has_judged_cases,
    init_db,
    investigation_tickets,
    mark_turn_done,
    queue_turn,
    record_challenge,
    redeem_attach_code,
    register_ticket,
    remove_lesson,
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

        The receiver is addressed by Role (*receiver_id*); an unknown Role is refused. The CEO is
        addressed as ``ceo``: no turn is queued, and the message is shown when the office is next opened.

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
        if receiver is None and receiver_id != "ceo":
            raise ValueError(
                f"unknown Role {receiver_id!r}; the Roles are: {', '.join(map(shown, CAST))}. The CEO is 'ceo'"
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

        if receiver and msg_type in ("DONE", "BLOCKED", "QUESTION"):
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
    db_path: Path | None = None, token: str | None = None, gh: Gh | None = None,
    on_attach: Callable[[], None] | None = None, project: Path | None = None,
) -> FastMCP:
    """The office server for one caller: every tool call is made as the holder of *token*.

    With *gh*, grants and tickets mirror to GitHub. With *project* (the main checkout), an answer
    at a gate removes the worktrees of the tickets whose pull requests are merged or closed, and a
    submitted Diagnosis or Retro is read from its ticket's branch. With *on_attach*, the server was started
    with no token (the plugin declares it for every session): it creates nothing and refuses
    every call until ``attach`` makes it the owner's, then calls *on_attach*.
    """
    if db_path is None:
        db_path = get_office_db_path()
    if not on_attach:
        init_db(db_path)

    server = FastMCP("claudarama")

    if on_attach:
        @server.tool()
        def attach(code: str) -> dict:
            """Make this session the CEO's Session. The code comes from `claudarama open --attach`,
            which the CEO runs as /claudarama:open."""
            nonlocal token
            owner = redeem_attach_code(db_path, code)
            if owner is None:
                raise PermissionError("unknown or used attach code: the CEO runs /claudarama:open for a new one")
            if not token:  # opening again in the same session only reloads the brief
                token = owner
                on_attach()
            return {"ok": True}

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
        """Send a message to a Role (receiver_id), or to the CEO as "ceo", and end your turn. The sender is taken from your token."""
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
    def grant(
        mandate: str, ticket: str, investigator: str = "researcher", challenger: str = "engineering-lead",
        judged_cases: str = "",
    ) -> dict:
        """Grant a mandate, naming its investigation ticket, its investigating Role, whose turn on
        that ticket is queued, and its challenging Role, a different Role that will try to refute
        the Diagnosis before the CEO sees it. `judged_cases` are the CEO's own cases of what is right
        and what is wrong, when the mandate has them: its Diagnosis must then report on them.
        Owner token only."""
        authenticate(db_path, token, owner_only=True)
        grant_mandate(db_path, mandate, ticket, investigator, challenger, judged_cases)
        if gh:
            sync(db_path, gh)
        return {"ok": True, "mandate": mandate, "ticket": ticket, "investigator": investigator, "challenger": challenger}

    @server.tool()
    def list_gates() -> dict:
        """The gates waiting for the CEO's answer, in the order of the loop. Owner token only."""
        authenticate(db_path, token, owner_only=True)
        return {"gates": [{"gate": g["gate"], "shows": g["shows"]} for g in open_gates(db_path, gh)]}

    @server.tool()
    def answer_gate(gate: str, answer: str, reason: str = "") -> dict:
        """Give the CEO's answer at a gate named by `list_gates`: YES, NO or DISCUSS. Owner token only.

        A NO needs the CEO's one-line reason: it goes to whoever produced the work, who is woken with it.
        DISCUSS leaves the gate open: talk it through with the CEO, then call again with their YES or NO."""
        authenticate(db_path, token, owner_only=True)
        answer = answer.strip().upper()
        if answer not in ("YES", "NO", "DISCUSS"):
            raise ValueError(f"answer {answer!r} is not YES, NO or DISCUSS")
        waiting = {g["gate"]: g for g in open_gates(db_path, gh)}
        if gate not in waiting:
            raise ValueError(f"no open gate {gate!r}; the open gates are: {', '.join(waiting) or 'none'}")
        if answer != "DISCUSS":
            waiting[gate]["resolve"](answer == "YES", reason)
        if project:  # whenever the CEO is at a gate: of a ticket merged or closed here, or withdrawn by its author
            remove_finished_worktrees(project, db_path, gh)
        if answer != "DISCUSS" and gate.startswith("pr:"):
            advance_to_learning(db_path, gh)  # a merged PR may have closed a mandate's last ticket
        return {"ok": True, "gate": gate, "answer": answer, "open": answer == "DISCUSS"}

    def submitted(mandate: str, path: str, directory: str, kind: str) -> tuple[str, str | None]:
        """The path of a submitted Diagnosis or Retro, refused outside its *directory*, and its text
        as committed on the branch of the mandate's investigation ticket, where an open pull request
        must hold it for the CEO's YES to merge. No text for a mandate granted with no such ticket."""
        path = document_path(path, directory, kind)
        ticket = investigation_tickets(db_path).get(mandate)
        if not (project and gh and ticket):
            return path, None
        text = committed(project, ticket, path, kind)
        open_pull_request(gh, ticket, kind)
        return path, text

    @server.tool(name="submit_diagnosis")
    def submit_diagnosis_tool(mandate: str, diagnosis_path: str) -> dict:
        """Submit a Diagnosis: the mandate's challenging Role is woken to challenge it. It reaches
        the CEO's Diagnosis gate only once the Challenge is recorded.

        `diagnosis_path` is `.claudarama/company/diagnoses/<name>.md`, from the project's root. Before
        you submit, commit the file on the ticket's branch and open a pull request from that branch:
        the CEO's YES merges it. A Diagnosis is refused unless it has the headings Measure, Rival
        explanations, Recommended strategy and, when the mandate has judged cases, Judged cases."""
        authenticate(db_path, token)
        diagnosis_path, text = submitted(mandate, diagnosis_path, DIAGNOSES, "Diagnosis")
        if text is not None and (missing := missing_sections(text, has_judged_cases(db_path, mandate))):
            raise ValueError(
                f"the Diagnosis at {diagnosis_path} lacks its required sections: {', '.join(missing)}. "
                "Each is a heading of that name"
            )
        submit_diagnosis(db_path, mandate, diagnosis_path)
        return {"ok": True, "mandate": mandate, "status": "INVESTIGATING", "blocked_on_ceo": False}

    @server.tool(name="record_challenge")
    def record_challenge_tool(mandate: str, verdict: str, reasons: str, ran: str) -> dict:
        """Record your Challenge of a mandate's submitted Diagnosis: STANDS or DISPUTED, with your
        reasons and what you ran. The challenger is taken from your token; only the mandate's
        challenging Role is accepted."""
        identity = authenticate(db_path, token)
        record_challenge(db_path, mandate, identity.person_id or "ceo", verdict, reasons, ran)
        return {"ok": True, "mandate": mandate, "verdict": verdict}

    @server.tool(name="submit_epic")
    def submit_epic_tool(mandate: str, tickets: dict[str, str]) -> dict:
        """Submit an Epic, the drafted tickets of a PLANNING mandate: it moves to EXECUTING and pauses for the CEO.

        `tickets` maps each ticket to the Role that will do it, such as {"12": "fullstack-engineer"};
        a Role with no role file is refused. The CEO's YES wakes each ticket's Role."""
        authenticate(db_path, token)
        submit_epic(db_path, mandate, tickets)
        return {"ok": True, "mandate": mandate, "status": "EXECUTING", "blocked_on_ceo": True, "tickets": tickets}

    @server.tool(name="submit_lessons")
    def submit_lessons_tool(mandate: str, lesson_path: str, lessons: list[dict] | None = None) -> dict:
        """Submit the Retro of a LEARNING mandate, at `lesson_path`, together with the Lessons it
        proposes: it moves to CLOSED and pauses for the CEO, whose YES merges the Retro and adopts them.

        `lesson_path` is `.claudarama/company/retros/<name>.md`, from the project's root. Before you
        submit, commit the file on the ticket's branch and open a pull request from that branch.

        `lessons` holds at most three, each {"text": one rule of at most 300 characters, "scope":
        "company" or the one Role it is for}, such as {"text": "...", "scope": "designer"}."""
        authenticate(db_path, token)
        lesson_path, _ = submitted(mandate, lesson_path, RETROS, "Retro")
        submit_lessons(db_path, mandate, lesson_path, lessons)
        return {"ok": True, "mandate": mandate, "status": "CLOSED", "blocked_on_ceo": True}

    @server.tool()
    def list_lessons() -> dict:
        """The adopted Lessons, each with the number it is removed by, its scope and the mandate
        whose Retro proposed it (none when the CEO adopted it directly). Owner token only."""
        authenticate(db_path, token, owner_only=True)
        return {"lessons": [
            {"lesson": lesson["id"], "text": lesson["text"], "scope": lesson["scope"], "mandate": lesson["mandate_id"]}
            for lesson in adopted_lessons(db_path)
        ]}

    @server.tool(name="adopt_lesson")
    def adopt_lesson_tool(text: str, scope: str = "company") -> dict:
        """Adopt a Lesson the CEO gave directly: one rule of at most 300 characters, scoped to
        "company" or to one Role. Every later brief in its scope loads it. Owner token only."""
        authenticate(db_path, token, owner_only=True)
        return {"ok": True, "lesson": adopt_lesson(db_path, text, scope), "scope": scope}

    @server.tool(name="remove_lesson")
    def remove_lesson_tool(lesson: int) -> dict:
        """Remove an adopted Lesson, by its number from `list_lessons`: no later brief loads it.
        Owner token only."""
        authenticate(db_path, token, owner_only=True)
        remove_lesson(db_path, lesson)
        return {"ok": True, "lesson": lesson}

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
        pull_request: int, head_commit: str, verdict: str, diagnosis_path: str, command: str, reason: str = ""
    ) -> dict:
        """Log a Ship-check verdict (SHIP or FAIL) for a PR's head commit, with the Diagnosis path
        and the verification command you ran. The reviewer is taken from your token; only the
        engineering-lead's verdict is accepted.

        A FAIL needs its one-line `reason`: it wakes the Role of the ticket you were woken on. That
        ticket's second FAIL stops it instead: the mandate returns to INVESTIGATING, the
        investigating Role is woken with both reasons, and the CEO is notified."""
        from claudarama.db import record_verdict
        identity = authenticate(db_path, token)
        reviewer_id = identity.person_id or "ceo"
        stopped = record_verdict(
            db_path, pull_request, head_commit, reviewer_id, verdict, diagnosis_path, command, reason, identity.ticket
        )
        if stopped:
            notify_ceo(stopped)
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

    def reconcile() -> None:  # catches hand-moved issues, and pull requests merged or closed outside the office
        while True:
            remove_finished_worktrees(get_project_root(), db_path, run_gh)  # at open, then every minute
            follow_github(db_path, run_gh)  # pull requests opened and tickets closed outside a turn
            time.sleep(60)
            sync(db_path, run_gh)

    offices: list[Supervisor] = []

    def announce() -> None:  # the CEO learns of a gate without opening the office to look
        for gate in watch_gates(db_path):
            notify_ceo(gate)

    def run_office() -> None:
        """The CEO's Session runs the office: transcripts stay with the office's state, outside the project."""
        threading.Thread(target=reconcile, daemon=True).start()
        threading.Thread(target=announce, daemon=True).start()
        office = Supervisor(db_path, get_project_root() / PACK_DIR_NAME, db_path.parent / "turns", gh=run_gh)
        offices.append(office)
        threading.Thread(target=office.run, daemon=True).start()

    # Handed no token, this is the server the plugin declares: it waits for /claudarama:open.
    server = create_mcp_server(
        db_path=db_path, token=token, gh=run_gh, on_attach=None if token else run_office, project=get_project_root(),
    )
    identity = resolve_token(db_path, token)
    if identity and identity.is_owner:  # a turn's server neither reconciles nor runs turns
        run_office()
    try:
        server.run()
    finally:  # the Session closed
        for office in offices:
            office.close()


if __name__ == "__main__":
    main()
