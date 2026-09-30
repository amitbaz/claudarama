import os
import sqlite3
import subprocess
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
    thread_with TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    model TEXT,
    branch TEXT,
    FOREIGN KEY(person_id) REFERENCES people(id)
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    sender TEXT NOT NULL,
    receiver TEXT NOT NULL,
    msg_type TEXT NOT NULL,
    ticket TEXT,
    body TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS briefs (
    turn_id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(turn_id) REFERENCES turns(id)
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
        # Databases created before messaging/escalation lack these columns.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(turns)")}
        for col in ("thread_with", "model", "branch"):
            if col not in cols:
                conn.execute(f"ALTER TABLE turns ADD COLUMN {col} TEXT")


def queue_turn(
    db_path: Path,
    person_id: str,
    thread_with: str | None = None,
    model: str | None = None,
    branch: str | None = None,
) -> str:
    """Create a new turn with status 'queued'. Returns the turn ID.

    *thread_with* is the person_id of the other participant in the active
    message thread. When set, the supervisor fetches the live thread from the
    ``messages`` table at run-time rather than duplicating its content here.
    """
    import uuid

    turn_id = str(uuid.uuid4())
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO turns (id, person_id, status, thread_with, model, branch) "
            "VALUES (?, ?, 'queued', ?, ?, ?)",
            (turn_id, person_id, thread_with, model, branch),
        )
    return turn_id


def get_queued_turns(db_path: Path) -> list[dict]:
    """Return all turns with status 'queued', oldest first."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT t.id, t.person_id, p.role FROM turns t "
            "JOIN people p ON t.person_id = p.id "
            "WHERE t.status = 'queued' ORDER BY t.started_at ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_turn(db_path: Path, turn_id: str) -> dict | None:
    """Return a turn row as a dict, or None if not found.

    The dict includes a ``thread_with`` key (the person_id of the other
    participant in the active message thread, or None). The supervisor uses
    this to call ``get_thread`` and inject the live thread into the brief.
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT t.id, t.person_id, t.status, t.thread_with, t.model, t.branch, p.role "
            "FROM turns t JOIN people p ON t.person_id = p.id "
            "WHERE t.id = ?",
            (turn_id,),
        ).fetchone()
    return dict(row) if row else None


def _set_turn_status(db_path: Path, turn_id: str, status: str) -> None:
    """Set a turn's status and, for terminal states, set ended_at."""
    terminal = {"done", "failed"}
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
) -> str:
    """Persist a message to the DB. Returns the new message ID."""
    import uuid

    msg_id = str(uuid.uuid4())
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO messages (id, sender, receiver, msg_type, ticket, body) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (msg_id, sender, receiver, msg_type, ticket, body),
        )
    return msg_id


def get_thread(db_path: Path, participants: tuple[str, str]) -> list[dict]:
    """Return all messages between two participants, oldest first.

    A message belongs to the thread if sender and receiver are the two
    participants (in either direction).
    """
    a, b = participants
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, sender, receiver, msg_type, ticket, body, created_at "
            "FROM messages "
            "WHERE (sender = ? AND receiver = ?) OR (sender = ? AND receiver = ?) "
            "ORDER BY created_at ASC",
            (a, b, b, a),
        ).fetchall()
    return [dict(r) for r in rows]

