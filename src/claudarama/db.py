import os
import sqlite3
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
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
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


def get_office_db_path(project_name: str | None = None) -> Path:
    """Return the office.db path for the given project, defaulting to current working dir name."""
    if not project_name:
        project_name = Path.cwd().name
    home = Path(os.environ.get("HOME", Path.home()))
    return home / ".claudarama" / project_name / "office.db"


def init_db(db_path: Path) -> None:
    """Initialize the SQLite database schema if not present."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
