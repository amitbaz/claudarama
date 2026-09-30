import os
import secrets
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS people (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    manager_id TEXT,
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
    kind TEXT NOT NULL,  -- 'turn', 'owner' or 'session'
    person_id TEXT,
    turn_id TEXT,
    ended_at TIMESTAMP   -- set when a 'session' token's session exits
);

CREATE TABLE IF NOT EXISTS mandates (
    id TEXT PRIMARY KEY,
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    mandate_id TEXT NOT NULL,
    hard INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(mandate_id) REFERENCES mandates(id)
);

CREATE TABLE IF NOT EXISTS briefs (
    turn_id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(turn_id) REFERENCES turns(id)
);

CREATE TABLE IF NOT EXISTS verdicts (
    pull_request INTEGER NOT NULL,
    head_commit TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    verdict TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (pull_request, head_commit, reviewer_id)
);
"""


def get_project_name() -> str:
    """Resolve project name from git or current directory."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            common_git_dir = Path(res.stdout.strip())
            # For common dir .git inside project root, parent is project dir
            if common_git_dir.name == ".git":
                return common_git_dir.parent.name
    except Exception:
        pass

    try:
        res = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            return Path(res.stdout.strip()).name
    except Exception:
        pass

    return Path.cwd().name


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
        # Databases created before messaging/escalation/threads lack these columns.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(turns)")}
        for col, decl in (
            ("thread", "TEXT"), ("model", "TEXT"), ("branch", "TEXT"),
            ("kind", "TEXT NOT NULL DEFAULT 'work'"), ("refusal", "TEXT"),
        ):
            if col not in cols:
                conn.execute(f"ALTER TABLE turns ADD COLUMN {col} {decl}")
        cols = {r[1] for r in conn.execute("PRAGMA table_info(messages)")}
        if "thread" not in cols:
            conn.execute("ALTER TABLE messages ADD COLUMN thread TEXT")
            # Pair-based messages that named a ticket join that ticket's thread.
            conn.execute(
                "UPDATE messages SET thread = 'ticket:' || ticket WHERE ticket IS NOT NULL"
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
) -> str:
    """Create a new turn with status 'queued'. Returns the turn ID.

    *kind* is 'work', 'ritual' or 'assistant'; only 'work' turns need a grant.

    *thread* is the key of the message thread that woke the turn. When set, the
    supervisor fetches the live thread from the ``messages`` table at run-time
    rather than duplicating its content here.
    """
    import uuid

    turn_id = str(uuid.uuid4())
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO turns (id, person_id, status, thread, model, branch, kind) "
            "VALUES (?, ?, 'queued', ?, ?, ?, ?)",
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
            "  AND NOT EXISTS (SELECT 1 FROM tokens WHERE kind = 'session' AND person_id = t.person_id AND ended_at IS NULL) "
            "  AND NOT EXISTS (SELECT 1 FROM turns WHERE status = 'running' AND person_id = t.person_id) "
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
            "SELECT t.id, t.person_id, t.status, t.thread, t.model, t.branch, t.kind, p.role "
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


def mark_turn_failed(db_path: Path, turn_id: str) -> None:
    """Mark a turn as failed and set ended_at."""
    _set_turn_status(db_path, turn_id, "failed")


def refuse_turn(db_path: Path, turn_id: str, reason: str) -> None:
    """End a queued turn without starting it, recording why."""
    _set_turn_status(db_path, turn_id, "refused")
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE turns SET refusal = ? WHERE id = ?", (reason, turn_id))


def grant_mandate(db_path: Path, mandate_id: str) -> None:
    """Record the CEO's grant of a mandate. Granting twice is harmless."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT OR IGNORE INTO mandates (id) VALUES (?)", (mandate_id,))


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

    kind: str  # 'turn', 'owner' or 'session'
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


def start_session(db_path: Path, person_id: str) -> str:
    """Record a ``talk`` session as open and return its token."""
    return _new_token(db_path, "session", person_id)


def end_session(db_path: Path, token: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE tokens SET ended_at = CURRENT_TIMESTAMP WHERE token = ? AND kind = 'session'",
            (token,),
        )


def has_open_session(db_path: Path, person_id: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT 1 FROM tokens WHERE kind = 'session' AND person_id = ? AND ended_at IS NULL",
            (person_id,),
        ).fetchone() is not None


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
        if row["kind"] == "session":
            live = row["ended_at"] is None
            return Identity("session", row["person_id"]) if live else None
        turn = conn.execute(
            "SELECT status, thread FROM turns WHERE id = ?", (row["turn_id"],)
        ).fetchone()
    if turn is None or turn["status"] != "running":
        return None
    thread = turn["thread"] or ""
    ticket = thread.removeprefix("ticket:") if thread.startswith("ticket:") else None
    return Identity("turn", row["person_id"], row["turn_id"], ticket)


def get_person_by_name(db_path: Path, name: str) -> dict | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM people WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else None

def record_verdict(db_path: Path, pull_request: int, head_commit: str, reviewer_id: str, verdict: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO verdicts (pull_request, head_commit, reviewer_id, verdict) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(pull_request, head_commit, reviewer_id) DO UPDATE SET verdict = excluded.verdict",
            (pull_request, head_commit, reviewer_id, verdict),
        )
