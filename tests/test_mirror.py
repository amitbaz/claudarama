"""GitHub milestone mirror (issue #36). `gh` is faked; nothing touches the network."""
import json
import sqlite3
from types import SimpleNamespace

from claudarama.daemon import create_mcp_server
from claudarama.db import get_owner_token, init_db, create_turn_token, mark_turn_running, queue_turn
from claudarama.mirror import sync


class FakeGh:
    """Just enough of GitHub: milestones by title and issue -> milestone title."""

    def __init__(self, issues=None):
        self.milestones, self.issues, self.comments = [], dict(issues or {}), []

    def __call__(self, args):
        if args[0] == "api" and "-f" in args:
            self.milestones.append(args[args.index("-f") + 1].removeprefix("title="))
        elif args[0] == "api":
            return "\n".join(self.milestones)
        elif args[:2] == ["issue", "view"]:
            m = self.issues.get(args[2])
            return json.dumps({"milestone": {"title": m} if m else None})
        elif args[:2] == ["issue", "edit"]:
            self.issues[args[2]] = args[args.index("--milestone") + 1]
        elif args[:2] == ["issue", "comment"]:
            self.comments.append((args[2], args[-1]))
        return ""


def _office(tmp_path, gh):
    db = tmp_path / "office.db"
    init_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO people (id, name, role) VALUES ('p1', 'Bender', 'engineer')")
    server = create_mcp_server(db_path=db, gh=gh)

    def call(token, tool, **args):
        ctx = SimpleNamespace(request_context=SimpleNamespace(request=SimpleNamespace(path_params={"token": token})))
        return server._tool_manager.get_tool(tool).fn(**args, ctx=ctx)

    turn = queue_turn(db, "p1")
    mark_turn_running(db, turn)
    return db, call, get_owner_token(db), create_turn_token(db, turn)


def test_grant_creates_milestone_and_ticket_lands_in_it(tmp_path):
    gh = FakeGh()
    db, call, owner, turn = _office(tmp_path, gh)
    call(owner, "grant", mandate="M1")
    assert gh.milestones == ["M1"]
    call(turn, "ticket_ready", ticket="7", mandate="M1")
    assert gh.issues == {"7": "M1"} and gh.comments == []


def test_hand_moved_issue_goes_back_with_a_comment(tmp_path):
    gh = FakeGh()
    db, call, owner, turn = _office(tmp_path, gh)
    call(owner, "grant", mandate="M1")
    call(turn, "ticket_ready", ticket="7", mandate="M1")
    gh.issues["7"] = "Other"
    sync(db, gh)
    assert gh.issues["7"] == "M1"
    assert len(gh.comments) == 1 and "Other" in gh.comments[0][1]
    sync(db, gh)
    assert len(gh.comments) == 1  # settled: no repeat comment
