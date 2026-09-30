"""One-way mirror of granted mandates and their tickets to GitHub milestones.

The DB is the authority. A mandate id is the milestone title; a ticket id is
the issue number. `gh` is injected so tests never touch the network.
"""
import json
import logging
import sqlite3
import subprocess
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

Gh = Callable[[list[str]], str]


def run_gh(args: list[str]) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def sync(db_path: Path, gh: Gh) -> None:
    """Make GitHub match the DB: a milestone per mandate, each ticket in its mandate's.

    An issue found in another milestone is moved back with a comment. Safe to
    repeat, so it also heals a `gh` call that failed earlier.
    """
    # ponytail: re-checks every ticket per call; track a mirrored milestone per ticket if that gets slow
    with sqlite3.connect(db_path) as conn:
        mandates = [r[0] for r in conn.execute("SELECT id FROM mandates")]
        tickets = conn.execute("SELECT id, mandate_id FROM tickets").fetchall()
    try:
        have = set(gh(["api", "repos/{owner}/{repo}/milestones?state=all", "--paginate", "--jq", ".[].title"]).split("\n"))
        for m in mandates:
            if m not in have:
                gh(["api", "repos/{owner}/{repo}/milestones", "-f", f"title={m}"])
    except subprocess.CalledProcessError as e:
        log.warning("milestone mirror failed: %s", e.stderr)
        return
    for ticket, mandate in tickets:
        try:
            view = gh(["issue", "view", ticket, "--json", "milestone"])
            current = (json.loads(view)["milestone"] or {}).get("title", "")
            if current == mandate:
                continue
            gh(["issue", "edit", ticket, "--milestone", mandate])
            if current:
                gh([
                    "issue", "comment", ticket, "--body",
                    f"Moved back from milestone {current!r} to {mandate!r}: "
                    "the office daemon owns milestones, one per granted mandate.",
                ])
        except subprocess.CalledProcessError as e:
            log.warning("ticket %s mirror failed: %s", ticket, e.stderr)
