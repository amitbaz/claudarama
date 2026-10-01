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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    diagnosis_path TEXT,
    lesson_path TEXT
);

CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    mandate_id TEXT NOT NULL,
    hard INTEGER NOT NULL DEFAULT 0,
    drafted INTEGER NOT NULL DEFAULT 0,  -- in an Epic awaiting the CEO's approval
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
            ("blocked_on_ceo", "INTEGER NOT NULL DEFAULT 0"),
            ("diagnosis_path", "TEXT"), ("lesson_path", "TEXT"),
        ):
            if col not in cols:
                conn.execute(f"ALTER TABLE mandates ADD COLUMN {col} {decl}")
        if "drafted" not in {r[1] for r in conn.execute("PRAGMA table_info(tickets)")}:
            conn.execute("ALTER TABLE tickets ADD COLUMN drafted INTEGER NOT NULL DEFAULT 0")
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
    """Return all turns with status 'queued', oldest first."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT t.id, t.person_id, p.role FROM turns t "
            "JOIN people p ON t.person_id = p.id "
            "WHERE t.status = 'queued' "
            "  AND t.started_at <= CURRENT_TIMESTAMP "
            "  AND NOT EXISTS (SELECT 1 FROM turns WHERE status = 'running' AND person_id = t.person_id) "
            "  AND NOT EXISTS (SELECT 1 FROM tickets k JOIN mandates m ON m.id = k.mandate_id "
            "                  WHERE m.blocked_on_ceo = 1 AND t.thread = 'ticket:' || k.id) "
            "ORDER BY t.started_at ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_turn(db_path: Path, turn_id: str) -> dict | None:
    """Return a turn row as a dict, or None if not found.

    The dict includes a ``thread`` key (the key of the message thread that
    woke the turn, or None). The supervisor uses this to call ``get_thread``
    and inject the live thread into the brief.
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT t.id, t.person_id, t.status, t.thread, t.model, t.branch, t.kind, t.error, p.role "
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


def grant_mandate(db_path: Path, mandate_id: str) -> None:
    """Record the CEO's grant of a mandate. Granting twice is harmless."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT OR IGNORE INTO mandates (id) VALUES (?)", (mandate_id,))


def submit_diagnosis(db_path: Path, mandate_id: str, diagnosis_path: str) -> None:
    """Move an INVESTIGATING mandate to PLANNING and pause it for the CEO's Diagnosis gate."""
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE mandates SET status = 'PLANNING', blocked_on_ceo = 1, diagnosis_path = ? "
            "WHERE id = ? AND status = 'INVESTIGATING'",
            (diagnosis_path, mandate_id),
        )
        if cur.rowcount == 0:
            raise ValueError(f"mandate {mandate_id!r} is not INVESTIGATING")


def diagnosis_gates(db_path: Path) -> list[dict]:
    """Mandates paused at the Diagnosis gate, awaiting the CEO."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, diagnosis_path FROM mandates "
            "WHERE blocked_on_ceo = 1 AND status = 'PLANNING' ORDER BY granted_at, rowid"
        ).fetchall()
    return [dict(r) for r in rows]


def resolve_diagnosis_gate(db_path: Path, mandate_id: str, approved: bool) -> None:
    """YES unblocks the mandate to plan; NO sends it back to INVESTIGATING, unblocked."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE mandates SET blocked_on_ceo = 0, status = ? "
            "WHERE id = ? AND blocked_on_ceo = 1 AND status = 'PLANNING'",
            ("PLANNING" if approved else "INVESTIGATING", mandate_id),
        )


def submit_epic(db_path: Path, mandate_id: str, tickets: list[str]) -> None:
    """Tie drafted tickets to a PLANNING mandate, move it to EXECUTING and pause it for the CEO."""
    if not tickets:
        raise ValueError("an Epic needs at least one ticket")
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE mandates SET status = 'EXECUTING', blocked_on_ceo = 1 "
            "WHERE id = ? AND status = 'PLANNING' AND blocked_on_ceo = 0",
            (mandate_id,),
        )
        if cur.rowcount == 0:
            raise ValueError(f"mandate {mandate_id!r} is not PLANNING and unblocked")
        try:
            conn.executemany(
                "INSERT INTO tickets (id, mandate_id, drafted) VALUES (?, ?, 1)",
                [(t, mandate_id) for t in tickets],
            )
        except sqlite3.IntegrityError as e:  # the with-block rolls the mandate update back
            raise ValueError("a ticket of the Epic already exists") from e


def epic_gates(db_path: Path) -> list[dict]:
    """Mandates paused at the Epic gate, with their drafted tickets, awaiting the CEO."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id FROM mandates WHERE blocked_on_ceo = 1 AND status = 'EXECUTING' "
            "ORDER BY granted_at, rowid"
        ).fetchall()
        return [
            {"id": r["id"], "tickets": [t[0] for t in conn.execute(
                "SELECT id FROM tickets WHERE mandate_id = ? AND drafted = 1 ORDER BY rowid", (r["id"],))]}
            for r in rows
        ]


def resolve_epic_gate(db_path: Path, mandate_id: str, approved: bool) -> None:
    """YES unblocks the mandate to execute; NO discards the drafted tickets and returns it to PLANNING."""
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE mandates SET blocked_on_ceo = 0, status = ? "
            "WHERE id = ? AND blocked_on_ceo = 1 AND status = 'EXECUTING'",
            ("EXECUTING" if approved else "PLANNING", mandate_id),
        )
        if cur.rowcount:
            if approved:
                conn.execute("UPDATE tickets SET drafted = 0 WHERE mandate_id = ?", (mandate_id,))
            else:
                conn.execute("DELETE FROM tickets WHERE mandate_id = ? AND drafted = 1", (mandate_id,))


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


def start_learning(db_path: Path, mandate_id: str) -> None:
    """Move an unblocked EXECUTING mandate to LEARNING: its work is merged."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE mandates SET status = 'LEARNING' "
            "WHERE id = ? AND status = 'EXECUTING' AND blocked_on_ceo = 0", (mandate_id,))


def submit_lessons(db_path: Path, mandate_id: str, lesson_path: str) -> None:
    """Move a LEARNING mandate to CLOSED and pause it for the CEO's Lesson gate."""
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE mandates SET status = 'CLOSED', blocked_on_ceo = 1, lesson_path = ? "
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


def resolve_lesson_gate(db_path: Path, mandate_id: str, approved: bool) -> None:
    """YES unblocks the mandate, finally CLOSED; NO returns it to LEARNING, unblocked."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE mandates SET blocked_on_ceo = 0, status = ? "
            "WHERE id = ? AND blocked_on_ceo = 1 AND status = 'CLOSED'",
            ("CLOSED" if approved else "LEARNING", mandate_id),
        )


def register_ticket(db_path: Path, ticket: str, mandate_id: str, hard: bool = False) -> None:
    """Put a ticket under a granted mandate; refuses an ungranted one."""
    with sqlite3.connect(db_path) as conn:
        if conn.execute("SELECT 1 FROM mandates WHERE id = ?", (mandate_id,)).fetchone() is None:
            raise PermissionError(f"mandate {mandate_id!r} is not granted")
        conn.execute(
            "INSERT INTO tickets (id, mandate_id, hard) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET mandate_id = excluded.mandate_id, hard = excluded.hard",
            (ticket, mandate_id, int(hard)),
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
    verdict: str, diagnosis_path: str, command: str,
) -> None:
    """Log a Ship-check verdict for a PR's head commit; a re-run on the same head replaces it.

    Only the engineering-lead may record one, so no author approves their own work.
    """
    if reviewer_id != "engineering-lead":
        raise PermissionError(
            f"a Ship-check verdict is accepted only from the engineering-lead, not from {shown(reviewer_id)}"
        )
    if verdict not in ("SHIP", "FAIL"):
        raise ValueError(f"verdict must be SHIP or FAIL, not {verdict!r}")
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
