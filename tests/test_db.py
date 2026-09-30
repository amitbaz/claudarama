"""Tests for database initialization and office schema."""
import sqlite3
from pathlib import Path

from claudarama.db import get_office_db_path, init_db


def test_get_office_db_path_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    db_path = get_office_db_path("my-project")
    expected = tmp_path / ".claudarama" / "my-project" / "office.db"
    assert db_path == expected


def test_init_db_creates_tables(tmp_path):
    db_path = tmp_path / "office.db"
    init_db(db_path)
    assert db_path.exists()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()

    expected_tables = {"people", "turns", "messages", "briefs"}
    assert expected_tables.issubset(tables)


def test_init_db_idempotent(tmp_path):
    db_path = tmp_path / "office.db"
    init_db(db_path)
    # Calling init_db again on existing database should not fail
    init_db(db_path)
    assert db_path.exists()
