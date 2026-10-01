import hashlib
import os
import secrets
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path


# The fixed cast: every Role and the name of its one Person. A Person's identifier is their Role.
CAST = {
    "assistant": "Nibbler",
    "pm": "Hermes",
    "engineering-lead": "Kif",
    "fullstack-engineer": "Bender",
    "frontend-engineer": "Fry",
    "database-architect": "Scruffy",
    "designer": "Zoidberg",
    "prompt-engineer": "Cubert",
    "eval-engineer": "Morbo",
    "researcher": "Amy",
}


def shown(role: str) -> str:
    """How a Person is shown: the Role first, the name beside it. Anyone else (the CEO) as given."""
    return f"{role} ({CAST[role]})" if role in CAST else role


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS people (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS turns (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL,
    status TEXT NOT NULL,
    thread TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    model TEXT,
    branch TEXT,
    kind TEXT NOT NULL DEFAULT 'work',  -- 'work', 'ritual' or 'assistant'
    refusal TEXT,
    error TEXT,  -- the error output of a failed launch
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_tokens INTEGER,
    cache_write_tokens INTEGER,
    cost REAL,
    FOREIGN KEY(person_id) REFERENCES people(id)
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    sender TEXT NOT NULL,
    receiver TEXT NOT NULL,
    msg_type TEXT NOT NULL,
    ticket TEXT,
    thread TEXT,
    body TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    shown INTEGER NOT NULL DEFAULT 0  -- a message to the CEO, once an open has shown it
);

CREATE TABLE IF NOT EXISTS tokens (
    token TEXT PRIMARY KEY,
    kind TEXT NOT NULL,  -- 'turn', 'owner' or 'attach' (a one-time code, never an identity)
    person_id TEXT,
    turn_id TEXT,
    ended_at TIMESTAMP   -- unused since `talk` was removed; kept so existing databases still match
);

CREATE TABLE IF NOT EXISTS mandates (
    id TEXT PRIMARY KEY,
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'INVESTIGATING'
        CHECK (status IN ('PROPOSED', 'INVESTIGATING', 'PLANNING', 'EXECUTING', 'LEARNING', 'CLOSED')),
    blocked_on_ceo INTEGER NOT NULL DEFAULT 0,
    pauses INTEGER NOT NULL DEFAULT 0,  -- how many times it has paused at a gate
    diagnosis_path TEXT,
    lesson_path TEXT,
    investigator TEXT NOT NULL DEFAULT 'researcher',  -- the investigating Role
    investigation_ticket TEXT,  -- its thread carries the mandate's own work: Diagnosis, Epic and Retro
    challenger TEXT NOT NULL DEFAULT 'engineering-lead',  -- the challenging Role, never the investigating Role
    awaiting_challenge INTEGER NOT NULL DEFAULT 0,  -- a Diagnosis is submitted and its Challenge is not yet recorded
    judged_cases TEXT NOT NULL DEFAULT ''  -- the CEO's judged cases; a Diagnosis of a mandate that has them reports on them
);

CREATE TABLE IF NOT EXISTS challenges (
    id INTEGER PRIMARY KEY,
    mandate_id TEXT NOT NULL,
    verdict TEXT NOT NULL,     -- 'STANDS' or 'DISPUTED'
    reasons TEXT NOT NULL,
    ran TEXT NOT NULL,         -- what the challenger ran
    challenger TEXT NOT NULL,  -- who recorded it
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(mandate_id) REFERENCES mandates(id)
);

CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    mandate_id TEXT NOT NULL,
    hard INTEGER NOT NULL DEFAULT 0,
    drafted INTEGER NOT NULL DEFAULT 0,  -- in an Epic awaiting the CEO's approval
    role TEXT,  -- the Role that does it: named by the Epic, or the investigating Role for an investigation ticket
    FOREIGN KEY(mandate_id) REFERENCES mandates(id)
);

CREATE TABLE IF NOT EXISTS briefs (
    turn_id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(turn_id) REFERENCES turns(id)
);

CREATE TABLE IF NOT EXISTS ticket_conversations (
    person_id TEXT NOT NULL,
    ticket TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    PRIMARY KEY (person_id, ticket)
);

CREATE TABLE IF NOT EXISTS working_notes (
    person_id TEXT NOT NULL,
    ticket TEXT NOT NULL,
    note TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (person_id, ticket)
);

CREATE TABLE IF NOT EXISTS verdicts (
    pull_request INTEGER NOT NULL,
    head_commit TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    verdict TEXT NOT NULL,
    diagnosis_path TEXT,  -- the Diagnosis evidence the check was run against
    command TEXT,         -- the verification command that was run
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (pull_request, head_commit, reviewer_id)
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL,
    ticket TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(person_id) REFERENCES people(id)
);

CREATE TABLE IF NOT EXISTS pull_requests (  -- each head commit the engineering-lead was woken to check
    number INTEGER NOT NULL,
    head_commit TEXT NOT NULL,
    PRIMARY KEY (number, head_commit)
);
"""


def get_project_root() -> Path:
    """The repository's main checkout, from any subdirectory or linked worktree of it.

    Outside a repository, the working directory.
    """
    root = Path.cwd().resolve()
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            # Relative to the working directory in a normal clone (".git"), so resolve it.
            common = Path(res.stdout.strip()).resolve()
            root = common.parent if common.name == ".git" else common
    except OSError:
        pass
    return root


def get_project_name() -> str:
    """Office identity: the main checkout's directory name plus a hash of its real path.

    The same from any subdirectory or linked worktree; two repositories that share a
    directory name differ by the hash.
    """
    root = get_project_root()
    digest = hashlib.sha256(str(root).encode()).hexdigest()[:8]
    return f"{root.name or 'office'}-{digest}"


def get_office_db_path(project_name: str | None = None) -> Path:
    """Return the office.db path for the given project, defaulting to current project name."""
    if not project_name:
        project_name = get_project_name()
    home = Path(os.environ.get("HOME", Path.home()))
    return home / ".claudarama" / project_name / "office.db"


def init_db(db_path: Path) -> None:
    """Initialize the SQLite database schema if not present."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        # Offices created before the fixed cast carry level and manager; they are gone.
        for col in {r[1] for r in conn.execute("PRAGMA table_info(people)")} & {"level", "manager_id"}:
            conn.execute(f"ALTER TABLE people DROP COLUMN {col}")
        conn.executemany(
            "INSERT OR IGNORE INTO people (id, name, role) VALUES (?, ?, ?)",
            [(role, name, role) for role, name in CAST.items()],
        )
        # Databases created before messaging/escalation/threads lack these columns.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(turns)")}
        for col, decl in (
            ("thread", "TEXT"), ("model", "TEXT"), ("branch", "TEXT"),
            ("kind", "TEXT NOT NULL DEFAULT 'work'"), ("refusal", "TEXT"), ("error", "TEXT"),
            ("input_tokens", "INTEGER"), ("output_tokens", "INTEGER"),
            ("cache_read_tokens", "INTEGER"), ("cache_write_tokens", "INTEGER"),
            ("cost", "REAL"),
        ):
            if col not in cols:
                conn.execute(f"ALTER TABLE turns ADD COLUMN {col} {decl}")
        cols = {r[1] for r in conn.execute("PRAGMA table_info(mandates)")}
        for col, decl in (
            ("status", "TEXT NOT NULL DEFAULT 'INVESTIGATING'"),
            ("blocked_on_ceo", "INTEGER NOT NULL DEFAULT 0"), ("pauses", "INTEGER NOT NULL DEFAULT 0"),
            ("diagnosis_path", "TEXT"), ("lesson_path", "TEXT"),
            ("investigator", "TEXT NOT NULL DEFAULT 'researcher'"), ("investigation_ticket", "TEXT"),
            ("challenger", "TEXT NOT NULL DEFAULT 'engineering-lead'"),
            ("awaiting_challenge", "INTEGER NOT NULL DEFAULT 0"), ("judged_cases", "TEXT NOT NULL DEFAULT ''"),
        ):
            if col not in cols:
                conn.execute(f"ALTER TABLE mandates ADD COLUMN {col} {decl}")
        cols = {r[1] for r in conn.execute("PRAGMA table_info(tickets)")}
        for col, decl in (("drafted", "INTEGER NOT NULL DEFAULT 0"), ("role", "TEXT")):
            if col not in cols:
                conn.execute(f"ALTER TABLE tickets ADD COLUMN {col} {decl}")
        cols = {r[1] for r in conn.execute("PRAGMA table_info(verdicts)")}
        for col in ("diagnosis_path", "command"):
            if col not in cols:
                conn.execute(f"ALTER TABLE verdicts ADD COLUMN {col} TEXT")
        cols = {r[1] for r in conn.execute("PRAGMA table_info(messages)")}
        if "thread" not in cols:
            conn.execute("ALTER TABLE messages ADD COLUMN thread TEXT")
            # Pair-based messages that named a ticket join that ticket's thread.
            conn.execute(
                "UPDATE messages SET thread = 'ticket:' || ticket WHERE ticket IS NOT NULL"
            )
        if "shown" not in cols:
            conn.execute("ALTER TABLE messages ADD COLUMN shown INTEGER NOT NULL DEFAULT 0")
        cols = {r[1] for r in conn.execute("PRAGMA table_info(checkpoints)")}
        if not cols:
            conn.executescript(
                "CREATE TABLE IF NOT EXISTS checkpoints ("
                "id TEXT PRIMARY KEY, person_id TEXT NOT NULL, ticket TEXT NOT NULL, "
                "content TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
                "FOREIGN KEY(person_id) REFERENCES people(id));"
            )


def thread_key(ticket: str | None, topic: str | None) -> str:
    """Key of the thread a message belongs to: its ticket, else its topic."""
    if ticket:
        return f"ticket:{ticket}"
    if topic:
        return f"topic:{topic}"
    raise ValueError("a message needs a ticket or a topic")


def queue_turn(
    db_path: Path,
    person_id: str,
    thread: str | None = None,
    model: str | None = None,
    branch: str | None = None,
    kind: str = "work",
    delay_minutes: float = 0,
) -> str:
    """Create a new turn with status 'queued'. Returns the turn ID.

    *kind* is 'work', 'ritual' or 'assistant'; only 'work' turns need a grant.

    *thread* is the key of the message thread that woke the turn. When set, the
    supervisor fetches the live thread from the ``messages`` table at run-time
    rather than duplicating its content here.
    """
    import uuid
    
    with sqlite3.connect(db_path) as conn:
        if thread and kind == "work":
            row = conn.execute(
                "SELECT id FROM turns WHERE person_id = ? AND thread = ? AND status = 'queued'",
                (person_id, thread)
            ).fetchone()
            if row:
                return row[0]

        turn_id = str(uuid.uuid4())
        delay_mod = f"+{delay_minutes} minutes" if delay_minutes else "+0 minutes"
        conn.execute(
            "INSERT INTO turns (id, person_id, status, thread, model, branch, kind, started_at) "
            f"VALUES (?, ?, 'queued', ?, ?, ?, ?, datetime('now', '{delay_mod}'))",
            (turn_id, person_id, thread, model, branch, kind),
        )
    return turn_id


def get_queued_turns(db_path: Path) -> list[dict]:
    """Return the queued turns that may start now, oldest first.

    A turn waits while its Person has one running, and while its ticket's mandate waits on the
    CEO. While a mandate is INVESTIGATING only its investigation ticket is worked on: a ticket's
    second FAIL sent it back, and the rest resumes once a revised Diagnosis passes its gate.
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT t.id, t.person_id, p.role FROM turns t "
            "JOIN people p ON t.person_id = p.id "
            "WHERE t.status = 'queued' "
            "  AND t.started_at <= CURRENT_TIMESTAMP "
            "  AND NOT EXISTS (SELECT 1 FROM turns WHERE status = 'running' AND person_id = t.person_id) "
            "  AND NOT EXISTS (SELECT 1 FROM tickets k JOIN mandates m ON m.id = k.mandate_id "
            # A mandate granted with no investigation ticket holds nothing back: `!=` against NULL is never true.
            "                  WHERE t.thread = 'ticket:' || k.id AND (m.blocked_on_ceo = 1 OR "
            "                         (m.status = 'INVESTIGATING' AND k.id != m.investigation_ticket))) "
            "ORDER BY t.started_at ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def ticket_has_turn(db_path: Path, ticket: str) -> bool:
    """True while a turn for *ticket* is queued or running."""
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT 1 FROM turns WHERE thread = ? AND status IN ('queued', 'running')", (f"ticket:{ticket}",)
        ).fetchone() is not None


def get_turn(db_path: Path, turn_id: str) -> dict | None:
    """Return a turn row as a dict, or None if not found.

    The dict includes a ``thread`` key (the key of the message thread that
    woke the turn, or None). The supervisor uses this to call ``get_thread``
    and inject the live thread into the brief.
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT t.id, t.person_id, t.status, t.thread, t.model, t.branch, t.kind, t.refusal, t.error, p.role "
            "FROM turns t JOIN people p ON t.person_id = p.id "
            "WHERE t.id = ?",
            (turn_id,),
        ).fetchone()
    return dict(row) if row else None


def _set_turn_status(db_path: Path, turn_id: str, status: str) -> None:
    """Set a turn's status and, for terminal states, set ended_at."""
    terminal = {"done", "failed", "refused"}
    with sqlite3.connect(db_path) as conn:
        if status in terminal:
            conn.execute(
                "UPDATE turns SET status = ?, ended_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, turn_id),
            )
        else:
            conn.execute(
                "UPDATE turns SET status = ? WHERE id = ?",
                (status, turn_id),
            )


def mark_turn_running(db_path: Path, turn_id: str) -> None:
    """Mark a turn as running."""
    _set_turn_status(db_path, turn_id, "running")


def mark_turn_done(db_path: Path, turn_id: str) -> None:
    """Mark a turn as done and set ended_at."""
    _set_turn_status(db_path, turn_id, "done")


def mark_turn_queued(db_path: Path, turn_id: str) -> None:
    _set_turn_status(db_path, turn_id, "queued")


def requeue_running_turns(db_path: Path) -> None:
    """Queue again every turn left running by a Session that closed; their old tokens stay dead."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM tokens WHERE turn_id IN (SELECT id FROM turns WHERE status = 'running')")
        conn.execute("UPDATE turns SET status = 'queued' WHERE status = 'running'")


def mark_turn_failed(db_path: Path, turn_id: str, error: str | None = None) -> None:
    """Mark a turn as failed and set ended_at, recording its error output when there is any."""
    _set_turn_status(db_path, turn_id, "failed")
    if error:
        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE turns SET error = ? WHERE id = ?", (error, turn_id))


def refuse_turn(db_path: Path, turn_id: str, reason: str) -> None:
    """End a queued turn without starting it, recording why."""
    _set_turn_status(db_path, turn_id, "refused")
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE turns SET refusal = ? WHERE id = ?", (reason, turn_id))


def save_turn_usage(db_path: Path, turn_id: str, usage: dict, model: str | None = None) -> None:
    """Save the usage and cost from a turn's result line."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE turns SET input_tokens = ?, output_tokens = ?, cache_read_tokens = ?, cache_write_tokens = ?, cost = ?, model = coalesce(?, model) WHERE id = ?",
            (
                usage.get("input_tokens") or usage.get("inputTokens") or 0,
                usage.get("output_tokens") or usage.get("outputTokens") or 0,
                usage.get("cache_read_tokens") or usage.get("cacheReadTokens") or 0,
                usage.get("cache_write_tokens") or usage.get("cacheWriteTokens") or 0,
                usage.get("cost") or usage.get("totalCost") or usage.get("total_cost") or 0.0,
                model,
                turn_id
            ),
        )


def grant_mandate(
    db_path: Path, mandate_id: str, ticket: str | None = None,
    investigator: str = "researcher", challenger: str = "engineering-lead", judged_cases: str = "",
) -> None:
    """Record the CEO's grant of a mandate, naming its investigating Role and its challenging Role,
    and wake the investigating Role on its investigation *ticket*. *judged_cases* are the CEO's own
    cases of what is right and what is wrong, when the mandate has them.

    Granting twice is harmless: the second grant changes nothing and wakes nobody.
    """
    for role in (investigator, challenger):
        if role not in CAST:
            raise ValueError(f"unknown Role {role!r}; the Roles are: {', '.join(map(shown, CAST))}")
    if challenger == investigator:
        raise ValueError(
            f"the challenging Role must differ from the investigating Role: both are the {shown(investigator)}"
        )
    with sqlite3.connect(db_path) as conn:
        new = conn.execute(
            "INSERT OR IGNORE INTO mandates (id, investigator, challenger, investigation_ticket, judged_cases) "
            "VALUES (?, ?, ?, ?, ?)",
            (mandate_id, investigator, challenger, ticket, judged_cases.strip()),
        ).rowcount
    if new and ticket:
        register_ticket(db_path, ticket, mandate_id, role=investigator)
        queue_turn(db_path, investigator, thread=thread_key(ticket, None))


def investigation_tickets(db_path: Path) -> dict[str, str]:
    """Each mandate's investigation ticket, whose branch carries the mandate's Diagnosis and Retro."""
    with sqlite3.connect(db_path) as conn:
        return dict(conn.execute(
            "SELECT id, investigation_ticket FROM mandates WHERE investigation_ticket IS NOT NULL"))


def has_judged_cases(db_path: Path, mandate_id: str) -> bool:
    """True when the CEO gave *mandate_id* judged cases at its grant."""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT 1 FROM mandates WHERE id = ? AND judged_cases != ''", (mandate_id,)).fetchone()
    return row is not None


def list_turns(db_path: Path) -> list[dict]:
    """Every turn with its Person and thread, in the order they were queued."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT id, person_id, thread FROM turns ORDER BY rowid")]


def mandate_states(db_path: Path) -> list[dict]:
    """Every mandate with its status and whether it waits on the CEO, in the order they were granted."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT id, status, blocked_on_ceo FROM mandates ORDER BY granted_at, rowid").fetchall()
    return [dict(r) for r in rows]


def pauses(db_path: Path) -> dict[str, int]:
    """For each mandate waiting on the CEO, how many times it has paused at a gate. A gate that
    closes and opens again shows the same, and this tells the two apart."""
    with sqlite3.connect(db_path) as conn:
        return dict(conn.execute("SELECT id, pauses FROM mandates WHERE blocked_on_ceo = 1"))


# What a submitted Diagnosis tells its challenging Role, whichever Role that is: it joins the thread
# the challenge turn's brief loads.
CHALLENGE_BRIEF = (
    "The Diagnosis of mandate {mandate!r} is submitted at {path}. You are its challenging Role: try to "
    "refute it before the CEO sees it. Do not trust the author's evidence; regenerate what the finding "
    "rests on. Ask: is the measure believable, and how much does it vary with nothing changed? What else "
    "could explain the evidence? What is missing? Then call `record_challenge` with STANDS or DISPUTED, "
    "your reasons and what you ran."
)


def submit_diagnosis(db_path: Path, mandate_id: str, diagnosis_path: str) -> None:
    """Record an INVESTIGATING mandate's Diagnosis and wake its challenging Role. The Diagnosis gate
    opens only once that Role's Challenge is recorded."""
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE mandates SET diagnosis_path = ?, awaiting_challenge = 1 "
            "WHERE id = ? AND status = 'INVESTIGATING' "
            "RETURNING investigator, challenger, investigation_ticket",
            (diagnosis_path, mandate_id),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"mandate {mandate_id!r} is not INVESTIGATING")
    investigator, challenger, ticket = row
    if ticket:  # a mandate granted before grants named an investigation ticket has none
        body = CHALLENGE_BRIEF.format(mandate=mandate_id, path=diagnosis_path)
        store_message(db_path, investigator, challenger, "DIAGNOSIS", body, ticket=ticket)
        queue_turn(db_path, challenger, thread=thread_key(ticket, None))


def record_challenge(db_path: Path, mandate_id: str, challenger_id: str, verdict: str, reasons: str, ran: str) -> None:
    """Store the Challenge of a submitted Diagnosis and open the Diagnosis gate: the mandate moves
    to PLANNING and pauses for the CEO, whatever the verdict.

    A mandate's first DISPUTED instead returns the Diagnosis to the investigating Role, woken with
    the reasons; the next submission reaches the CEO with its verdict either way.

    Only the mandate's challenging Role may record one, so no author clears their own finding.
    """
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT challenger, awaiting_challenge, investigator, investigation_ticket FROM mandates WHERE id = ?",
            (mandate_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"mandate {mandate_id!r} is not granted")
        challenger, awaiting, investigator, ticket = row
        if challenger_id != challenger:
            raise PermissionError(
                f"a Challenge of mandate {mandate_id!r} is accepted only from the {shown(challenger)}, "
                f"its challenging Role, not from {shown(challenger_id)}"
            )
        if verdict not in ("STANDS", "DISPUTED"):
            raise ValueError(f"verdict must be STANDS or DISPUTED, not {verdict!r}")
        if not reasons.strip() or not ran.strip():
            raise ValueError("a Challenge needs its reasons and what the challenger ran")
        if not awaiting:
            raise ValueError(f"mandate {mandate_id!r} has no Diagnosis waiting for a Challenge")
        conn.execute(
            "INSERT INTO challenges (mandate_id, verdict, reasons, ran, challenger) VALUES (?, ?, ?, ?, ?)",
            (mandate_id, verdict, reasons, ran, challenger_id),
        )
        returned = verdict == "DISPUTED" and conn.execute(
            "SELECT COUNT(*) FROM challenges WHERE mandate_id = ? AND verdict = 'DISPUTED'", (mandate_id,)
        ).fetchone()[0] == 1
        conn.execute(
            "UPDATE mandates SET awaiting_challenge = 0"
            + ("" if returned else ", status = 'PLANNING', blocked_on_ceo = 1, pauses = pauses + 1") + " WHERE id = ?",
            (mandate_id,),
        )
    if returned and ticket:  # a mandate granted before grants named an investigation ticket has none
        store_message(db_path, challenger, investigator, "DISPUTED", f"{reasons}\nWhat was run: {ran}", ticket=ticket)
        queue_turn(db_path, investigator, thread=thread_key(ticket, None))


def diagnosis_gates(db_path: Path) -> list[dict]:
    """Mandates paused at the Diagnosis gate, awaiting the CEO, each with the Challenge of its Diagnosis:
    ``verdict``, ``reasons``, ``ran`` and ``challenger``."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT m.id, m.diagnosis_path, c.verdict, c.reasons, c.ran, c.challenger FROM mandates m "
            "LEFT JOIN challenges c ON c.id = (SELECT MAX(id) FROM challenges WHERE mandate_id = m.id) "
            "WHERE m.blocked_on_ceo = 1 AND m.status = 'PLANNING' ORDER BY m.granted_at, m.rowid"
        ).fetchall()
    return [dict(r) for r in rows]


def one_line(reason: str, answer: str = "NO") -> str:
    """The reason for a NO or a FAIL, on one line. One without a reason is refused."""
    reason = " ".join(reason.split())
    if not reason:
        raise ValueError(f"a {answer} needs a one-line reason")
    return reason


def wake(db_path: Path, role: str, ticket: str, no: str | None = None) -> None:
    """Queue *role*'s turn on *ticket*'s thread. *no* is the gate the CEO answered NO at and the
    reason: it joins that thread first, so the turn's brief carries it."""
    if no:
        store_message(db_path, "ceo", role, "NO", no, ticket=ticket)
    queue_turn(db_path, role, thread=thread_key(ticket, None))


def ticket_role(db_path: Path, ticket: str) -> str | None:
    """The Role that does *ticket*, or None when the ticket names none."""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT role FROM tickets WHERE id = ?", (ticket,)).fetchone()
    return row[0] if row else None


def _wake_on_investigation_ticket(db_path: Path, mandate_id: str, role: str | None, no: str | None = None) -> None:
    """``wake`` on the mandate's investigation ticket; with no *role*, the investigating Role."""
    with sqlite3.connect(db_path) as conn:
        investigator, ticket = conn.execute(
            "SELECT investigator, investigation_ticket FROM mandates WHERE id = ?", (mandate_id,)).fetchone()
    if ticket:  # a mandate granted before grants named an investigation ticket has none
        wake(db_path, role or investigator, ticket, no)


def resolve_diagnosis_gate(db_path: Path, mandate_id: str, approved: bool, reason: str = "") -> None:
    """YES unblocks the mandate to plan and wakes the pm; NO sends it back to INVESTIGATING,
    unblocked, and wakes the investigating Role with the CEO's *reason*."""
    no = None if approved else f"Diagnosis gate: {one_line(reason)}"
    with sqlite3.connect(db_path) as conn:
        resolved = conn.execute(
            "UPDATE mandates SET blocked_on_ceo = 0, status = ? "
            "WHERE id = ? AND blocked_on_ceo = 1 AND status = 'PLANNING'",
            ("PLANNING" if approved else "INVESTIGATING", mandate_id),
        ).rowcount
    if resolved:
        _wake_on_investigation_ticket(db_path, mandate_id, "pm" if approved else None, no)


def submit_epic(db_path: Path, mandate_id: str, tickets: dict[str, str]) -> None:
    """Tie drafted *tickets*, each with the Role that will do it, to a PLANNING mandate, move it to
    EXECUTING and pause it for the CEO. A Role with no role file is refused."""
    from claudarama.brief import ROLES_DIR  # the brief builder imports this module

    if not tickets:
        raise ValueError("an Epic needs at least one ticket")
    for ticket, role in tickets.items():
        if role not in CAST or not (ROLES_DIR / f"{role}.md").is_file():
            raise ValueError(
                f"ticket {ticket!r} names {role!r}, a Role with no role file; the Roles are: {', '.join(map(shown, CAST))}"
            )
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE mandates SET status = 'EXECUTING', blocked_on_ceo = 1, pauses = pauses + 1 "
            "WHERE id = ? AND status = 'PLANNING' AND blocked_on_ceo = 0",
            (mandate_id,),
        )
        if cur.rowcount == 0:
            raise ValueError(f"mandate {mandate_id!r} is not PLANNING and unblocked")
        try:
            conn.executemany(
                "INSERT INTO tickets (id, mandate_id, drafted, role) VALUES (?, ?, 1, ?)",
                [(ticket, mandate_id, role) for ticket, role in tickets.items()],
            )
        except sqlite3.IntegrityError as e:  # the with-block rolls the mandate update back
            raise ValueError("a ticket of the Epic already exists") from e


def epic_gates(db_path: Path) -> list[dict]:
    """Mandates paused at the Epic gate, awaiting the CEO, each with its drafted tickets and their Roles."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id FROM mandates WHERE blocked_on_ceo = 1 AND status = 'EXECUTING' "
            "ORDER BY granted_at, rowid"
        ).fetchall()
        return [
            {"id": r["id"], "tickets": dict(conn.execute(
                "SELECT id, role FROM tickets WHERE mandate_id = ? AND drafted = 1 ORDER BY rowid", (r["id"],)))}
            for r in rows
        ]


def resolve_epic_gate(db_path: Path, mandate_id: str, approved: bool, reason: str = "") -> None:
    """YES unblocks the mandate to execute and wakes each drafted ticket's Role; NO discards the
    drafted tickets, returns it to PLANNING and wakes the pm with the CEO's *reason*."""
    no = None if approved else f"Epic gate: {one_line(reason)}"
    started: dict[str, str] = {}
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE mandates SET blocked_on_ceo = 0, status = ? "
            "WHERE id = ? AND blocked_on_ceo = 1 AND status = 'EXECUTING'",
            ("EXECUTING" if approved else "PLANNING", mandate_id),
        )
        if cur.rowcount:
            if approved:
                started = dict(conn.execute(
                    "SELECT id, role FROM tickets WHERE mandate_id = ? AND drafted = 1 ORDER BY rowid", (mandate_id,)))
                conn.execute("UPDATE tickets SET drafted = 0 WHERE mandate_id = ?", (mandate_id,))
            else:
                conn.execute("DELETE FROM tickets WHERE mandate_id = ? AND drafted = 1", (mandate_id,))
    if cur.rowcount and no:
        _wake_on_investigation_ticket(db_path, mandate_id, "pm", no)
    for ticket, role in started.items():
        wake(db_path, role, ticket)


def tickets_by_mandate(db_path: Path, status: str) -> dict[str, list[str]]:
    """Ticket ids of each unblocked mandate in *status*."""
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT m.id, k.id FROM mandates m JOIN tickets k ON k.mandate_id = m.id "
            "WHERE m.status = ? AND m.blocked_on_ceo = 0 ORDER BY k.rowid", (status,)).fetchall()
    out: dict[str, list[str]] = {}
    for mandate, ticket in rows:
        out.setdefault(mandate, []).append(ticket)
    return out


def mandates_of_tickets(db_path: Path, tickets: list[str]) -> list[str]:
    """Mandates that own any of *tickets* (office ticket ids)."""
    with sqlite3.connect(db_path) as conn:
        return sorted({r[0] for t in tickets for r in conn.execute(
            "SELECT mandate_id FROM tickets WHERE id = ?", (t,))})


def ship_checked(db_path: Path, pull_request: int, head_commit: str) -> bool:
    """True when a SHIP verdict is recorded for the PR's head commit."""
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT 1 FROM verdicts WHERE pull_request = ? AND head_commit = ? AND verdict = 'SHIP'",
            (pull_request, head_commit)).fetchone() is not None


def shipped(db_path: Path) -> list[tuple[int, str]]:
    """Each pull request and head commit with a SHIP verdict, oldest first."""
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT pull_request, head_commit FROM verdicts WHERE verdict = 'SHIP' ORDER BY rowid").fetchall()


def is_new_head(db_path: Path, pull_request: int, head_commit: str) -> bool:
    """True the first time the office sees *head_commit* on *pull_request*: the pull request
    opened, or took a new push."""
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "INSERT OR IGNORE INTO pull_requests (number, head_commit) VALUES (?, ?)", (pull_request, head_commit)
        ).rowcount == 1


def start_learning(db_path: Path, mandate_id: str) -> None:
    """Move an unblocked EXECUTING mandate to LEARNING, its work merged, and wake the
    engineering-lead to write the Retro."""
    with sqlite3.connect(db_path) as conn:
        moved = conn.execute(
            "UPDATE mandates SET status = 'LEARNING' "
            "WHERE id = ? AND status = 'EXECUTING' AND blocked_on_ceo = 0", (mandate_id,)).rowcount
    if moved:
        _wake_on_investigation_ticket(db_path, mandate_id, "engineering-lead")


def submit_lessons(db_path: Path, mandate_id: str, lesson_path: str) -> None:
    """Move a LEARNING mandate to CLOSED and pause it for the CEO's Lesson gate."""
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE mandates SET status = 'CLOSED', blocked_on_ceo = 1, pauses = pauses + 1, lesson_path = ? "
            "WHERE id = ? AND status = 'LEARNING' AND blocked_on_ceo = 0",
            (lesson_path, mandate_id),
        )
        if cur.rowcount == 0:
            raise ValueError(f"mandate {mandate_id!r} is not LEARNING")


def lesson_gates(db_path: Path) -> list[dict]:
    """Mandates paused at the Lesson gate, awaiting the CEO."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, lesson_path FROM mandates "
            "WHERE blocked_on_ceo = 1 AND status = 'CLOSED' ORDER BY granted_at, rowid"
        ).fetchall()
    return [dict(r) for r in rows]


def resolve_lesson_gate(db_path: Path, mandate_id: str, approved: bool, reason: str = "") -> None:
    """YES unblocks the mandate, finally CLOSED; NO returns it to LEARNING, unblocked, and wakes
    the engineering-lead, who wrote the Retro, with the CEO's *reason*."""
    no = None if approved else f"Lesson gate: {one_line(reason)}"
    with sqlite3.connect(db_path) as conn:
        resolved = conn.execute(
            "UPDATE mandates SET blocked_on_ceo = 0, status = ? "
            "WHERE id = ? AND blocked_on_ceo = 1 AND status = 'CLOSED'",
            ("CLOSED" if approved else "LEARNING", mandate_id),
        ).rowcount
    if resolved and no:
        _wake_on_investigation_ticket(db_path, mandate_id, "engineering-lead", no)


def register_ticket(db_path: Path, ticket: str, mandate_id: str, hard: bool = False, role: str | None = None) -> None:
    """Put a ticket under a granted mandate, with the *role* that does it when one is named;
    refuses an ungranted one."""
    with sqlite3.connect(db_path) as conn:
        if conn.execute("SELECT 1 FROM mandates WHERE id = ?", (mandate_id,)).fetchone() is None:
            raise PermissionError(f"mandate {mandate_id!r} is not granted")
        conn.execute(
            "INSERT INTO tickets (id, mandate_id, hard, role) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET mandate_id = excluded.mandate_id, hard = excluded.hard, "
            "role = coalesce(excluded.role, role)",
            (ticket, mandate_id, int(hard), role),
        )


def grant_refusal(db_path: Path, turn: dict) -> str | None:
    """Why a turn may not start, or None when it may.

    Ritual and Assistant turns need no grant. Any other turn needs a ticket
    (its own, or its thread's when it is a reply) under a granted mandate.
    """
    if turn["kind"] in ("ritual", "assistant") or turn["role"] == "assistant":
        return None
    thread = turn["thread"] or ""
    if not thread.startswith("ticket:"):
        return "no ticket: register one under a granted mandate first"
    ticket = thread.removeprefix("ticket:")
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket,)).fetchone()
    return None if row else f"ticket {ticket!r} is not under a granted mandate"


def save_brief(db_path: Path, turn_id: str, content: str) -> None:
    """Save the assembled brief for a turn."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO briefs (turn_id, content) VALUES (?, ?)",
            (turn_id, content),
        )


def save_checkpoint(db_path: Path, person_id: str, ticket: str, content: str) -> None:
    """Save a checkpoint for a person and ticket."""
    import uuid
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO checkpoints (id, person_id, ticket, content) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), person_id, ticket, content),
        )


def store_message(
    db_path: Path,
    sender: str,
    receiver: str,
    msg_type: str,
    body: str,
    ticket: str | None = None,
    topic: str | None = None,
) -> str:
    """Persist a message to the DB in its ticket or topic thread. Returns the new message ID."""
    import uuid

    thread = thread_key(ticket, topic)
    msg_id = str(uuid.uuid4())
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO messages (id, sender, receiver, msg_type, ticket, thread, body) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (msg_id, sender, receiver, msg_type, ticket, thread, body),
        )
    return msg_id


def ceo_messages(db_path: Path) -> list[dict]:
    """The messages addressed to the CEO that no open has shown yet, oldest first."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, sender, msg_type, thread, body FROM messages "
            "WHERE receiver = 'ceo' AND shown = 0 ORDER BY created_at, rowid"
        ).fetchall()
    return [dict(r) for r in rows]


def mark_shown(db_path: Path, messages: list[dict]) -> None:
    """Record that an open showed these messages to the CEO."""
    with sqlite3.connect(db_path) as conn:
        conn.executemany("UPDATE messages SET shown = 1 WHERE id = ?", [(m["id"],) for m in messages])


def get_thread(db_path: Path, thread: str) -> list[dict]:
    """Return all messages in a thread, oldest first."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, sender, receiver, msg_type, ticket, body, created_at "
            "FROM messages WHERE thread = ? ORDER BY created_at ASC, rowid ASC",
            (thread,),
        ).fetchall()
    return [dict(r) for r in rows]


@dataclass
class Identity:
    """Who a token speaks for. ``person_id`` is None for the owner."""

    kind: str  # 'turn' or 'owner'
    person_id: str | None = None
    turn_id: str | None = None
    ticket: str | None = None  # from the turn's thread, when it is a ticket thread

    @property
    def is_owner(self) -> bool:
        return self.kind == "owner"


def _new_token(db_path: Path, kind: str, person_id: str | None = None, turn_id: str | None = None) -> str:
    token = secrets.token_urlsafe(32)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO tokens (token, kind, person_id, turn_id) VALUES (?, ?, ?, ?)",
            (token, kind, person_id, turn_id),
        )
    return token


def create_turn_token(db_path: Path, turn_id: str) -> str:
    """Mint the secret for a turn. It stops working when the turn is done or failed."""
    turn = get_turn(db_path, turn_id)
    return _new_token(db_path, "turn", turn["person_id"], turn_id)


def get_owner_token(db_path: Path) -> str:
    """Return the owner token, creating it on first use."""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT token FROM tokens WHERE kind = 'owner'").fetchone()
    return row[0] if row else _new_token(db_path, "owner")


def create_attach_code(db_path: Path) -> str:
    """Mint the one-time code that lets a server process started without a token become the
    owner's (the plugin door). Only the newest code works."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM tokens WHERE kind = 'attach'")
    return _new_token(db_path, "attach")


def redeem_attach_code(db_path: Path, code: str) -> str | None:
    """Spend an attach code: the owner token, or None when the code is unknown or already spent."""
    if not db_path.exists():  # nothing was opened; connecting would create an empty database
        return None
    with sqlite3.connect(db_path) as conn:
        spent = conn.execute("DELETE FROM tokens WHERE token = ? AND kind = 'attach'", (code,)).rowcount
    return get_owner_token(db_path) if spent else None


def resolve_token(db_path: Path, token: str | None) -> Identity | None:
    """Identity for a live token; None when missing, unknown or dead."""
    if not token:
        return None
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM tokens WHERE token = ?", (token,)).fetchone()
        if row is None:
            return None
        if row["kind"] == "owner":
            return Identity("owner")
        turn = conn.execute(
            "SELECT status, thread FROM turns WHERE id = ?", (row["turn_id"],)
        ).fetchone()
    if turn is None or turn["status"] != "running":
        return None
    thread = turn["thread"] or ""
    ticket = thread.removeprefix("ticket:") if thread.startswith("ticket:") else None
    return Identity("turn", row["person_id"], row["turn_id"], ticket)


def get_person_by_role(db_path: Path, role: str) -> dict | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT id, name, role FROM people WHERE role = ?", (role,)).fetchone()
    return dict(row) if row else None


def record_verdict(
    db_path: Path, pull_request: int, head_commit: str, reviewer_id: str,
    verdict: str, diagnosis_path: str, command: str, reason: str = "", ticket: str | None = None,
) -> str | None:
    """Log a Ship-check verdict for a PR's head commit; a re-run on the same head replaces it.

    Only the engineering-lead may record one, so no author approves their own work.

    A FAIL needs its one-line *reason*, which goes to the Role of *ticket*, the ticket the check
    was made on. The ticket's second FAIL stops it instead: returns what the CEO is to be told.
    """
    if reviewer_id != "engineering-lead":
        raise PermissionError(
            f"a Ship-check verdict is accepted only from the engineering-lead, not from {shown(reviewer_id)}"
        )
    if verdict not in ("SHIP", "FAIL"):
        raise ValueError(f"verdict must be SHIP or FAIL, not {verdict!r}")
    if verdict == "FAIL":
        reason = one_line(reason, "FAIL")
    if not diagnosis_path.strip() or not command.strip():
        raise ValueError("a Ship-check needs the Diagnosis path and the command that was run")
    with sqlite3.connect(db_path) as conn:
        if conn.execute("SELECT 1 FROM mandates WHERE diagnosis_path = ?", (diagnosis_path,)).fetchone() is None:
            raise ValueError(f"no mandate has submitted a Diagnosis at {diagnosis_path!r}")
        conn.execute(
            "INSERT INTO verdicts (pull_request, head_commit, reviewer_id, verdict, diagnosis_path, command) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(pull_request, head_commit, reviewer_id) DO UPDATE SET "
            "verdict = excluded.verdict, diagnosis_path = excluded.diagnosis_path, command = excluded.command",
            (pull_request, head_commit, reviewer_id, verdict, diagnosis_path, command),
        )
    if verdict == "FAIL" and ticket and (role := ticket_role(db_path, ticket)):
        return _fail(db_path, ticket, role, f"Ship-check of #{pull_request}: {reason}")
    return None


def _fail(db_path: Path, ticket: str, role: str, reason: str) -> str | None:
    """A FAIL on *ticket* joins its thread. The first wakes the ticket's *role* with the reason.
    From the second on the ticket is stopped: its mandate returns to INVESTIGATING and the
    investigating Role is woken with every reason so far. Returns what the CEO is told then."""
    store_message(db_path, "engineering-lead", role, "FAIL", reason, ticket=ticket)
    # FAILs are counted per ticket as the FAIL messages in its thread.
    fails = [m["body"] for m in get_thread(db_path, thread_key(ticket, None)) if m["msg_type"] == "FAIL"]
    if len(fails) < 2:
        wake(db_path, role, ticket)
        return None
    with sqlite3.connect(db_path) as conn:
        mandate, investigator, investigation_ticket = conn.execute(
            "SELECT m.id, m.investigator, m.investigation_ticket FROM tickets k JOIN mandates m ON m.id = k.mandate_id "
            "WHERE k.id = ?", (ticket,)).fetchone()
        conn.execute(  # a mandate waiting at a gate stays there for the CEO's answer
            "UPDATE mandates SET status = 'INVESTIGATING' "
            "WHERE id = ? AND status IN ('PLANNING', 'EXECUTING') AND blocked_on_ceo = 0", (mandate,))
    failed = f"Ticket {ticket} failed its Ship-check {len(fails)} times"
    if investigation_ticket:  # a mandate granted before grants named an investigation ticket has none
        reasons = " ".join(f"{n}) {fail}" for n, fail in enumerate(fails, 1))
        store_message(db_path, "engineering-lead", investigator, "STOPPED", f"{failed}. {reasons}", ticket=investigation_ticket)
        wake(db_path, investigator, investigation_ticket)
    return f"{failed}: mandate {mandate!r} is back with the {shown(investigator)}"


def set_working_note(db_path: Path, person_id: str, ticket: str, note: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO working_notes (person_id, ticket, note, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(person_id, ticket) DO UPDATE SET note = excluded.note, updated_at = CURRENT_TIMESTAMP",
            (person_id, ticket, note),
        )

def get_working_note(db_path: Path, person_id: str, ticket: str) -> str | None:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT note FROM working_notes WHERE person_id = ? AND ticket = ?",
            (person_id, ticket),
        ).fetchone()
    return row[0] if row else None

def is_ticket_hard(db_path: Path, ticket: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT hard FROM tickets WHERE id = ?", (ticket,)).fetchone()
    return bool(row and row[0])


def save_ticket_conversation(db_path: Path, person_id: str, ticket: str, conversation_id: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO ticket_conversations (person_id, ticket, conversation_id) VALUES (?, ?, ?) "
            "ON CONFLICT(person_id, ticket) DO UPDATE SET conversation_id=excluded.conversation_id",
            (person_id, ticket, conversation_id)
        )

def get_ticket_conversation(db_path: Path, person_id: str, ticket: str) -> str | None:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("SELECT conversation_id FROM ticket_conversations WHERE person_id = ? AND ticket = ?", (person_id, ticket))
        row = cursor.fetchone()
        return row[0] if row else None

def ticket_from_thread(thread: str | None) -> str | None:
    if thread and thread.startswith("ticket:"):
        return thread[7:]
    return None
