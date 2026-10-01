"""An office resolves to one place per repository, wherever the CEO runs a command."""
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest

from claudarama.db import get_office_db_path, get_project_name, init_db


def git(cwd: Path, *args: str) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=env)


def make_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "-q")
    git(path, "commit", "-q", "--allow-empty", "-m", "init")
    return path


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    return h


def test_root_subdirectory_and_worktree_resolve_to_the_same_office(tmp_path, home, monkeypatch):
    repo = make_repo(tmp_path / "work" / "shop")
    sub = repo / "a" / "b"
    sub.mkdir(parents=True)
    wt = tmp_path / "wt" / "ticket-1"
    git(repo, "worktree", "add", "-q", "-b", "t1", str(wt))
    wt_sub = wt / "deep"
    wt_sub.mkdir()

    paths = set()
    for where in (repo, sub, wt, wt_sub):
        monkeypatch.chdir(where)
        paths.add(get_office_db_path())
    assert len(paths) == 1


def test_same_named_repositories_get_separate_offices(tmp_path, home, monkeypatch):
    one = make_repo(tmp_path / "x" / "shop")
    two = make_repo(tmp_path / "y" / "shop")
    monkeypatch.chdir(one)
    db_one = get_office_db_path()
    monkeypatch.chdir(two)
    db_two = get_office_db_path()
    assert db_one != db_two
    init_db(db_one)
    init_db(db_two)
    with sqlite3.connect(db_one) as conn:
        conn.execute("INSERT INTO people (id, name, role) VALUES ('p', 'n', 'pm')")
    with sqlite3.connect(db_two) as conn:
        assert conn.execute("SELECT count(*) FROM people").fetchone()[0] == 0


def test_name_is_never_empty_or_a_dot_in_a_normal_clone(tmp_path, home, monkeypatch):
    repo = make_repo(tmp_path / "shop")
    monkeypatch.chdir(repo)  # git reports the common dir as the relative ".git" here
    name = get_project_name()
    assert name.startswith("shop-")
    assert name not in ("", ".", "..")


def test_office_state_lives_under_home_outside_the_project(tmp_path, home, monkeypatch):
    repo = make_repo(tmp_path / "shop")
    monkeypatch.chdir(repo)
    db_path = get_office_db_path()
    assert home in db_path.parents
    assert repo not in db_path.parents


def test_database_and_schema_appear_on_first_use(tmp_path, home, monkeypatch):
    repo = make_repo(tmp_path / "shop")
    monkeypatch.chdir(repo)
    db_path = get_office_db_path()
    assert not db_path.exists()
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"people", "turns", "mandates", "tickets"} <= tables


def test_outside_a_repository_falls_back_to_the_directory(tmp_path, home, monkeypatch):
    plain = tmp_path / "scratch"
    plain.mkdir()
    monkeypatch.chdir(plain)
    assert get_project_name().startswith("scratch-")
