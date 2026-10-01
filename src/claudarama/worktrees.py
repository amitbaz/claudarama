"""A worktree and a branch for each ticket (spec #79, "Worktrees and documents").

They sit beside the main checkout, in ``<checkout>-worktrees/ticket-<id>`` on the branch
``ticket-<id>``: outside the checkout, so the CEO's own is never switched to another branch, and
outside the office's state directory, which no turn may reach.
"""
import json
import subprocess
import threading
from pathlib import Path

from claudarama.db import ticket_has_turn
from claudarama.mirror import Gh

_adding = threading.Lock()  # two turns starting on one new ticket add its worktree once


def worktrees_root(project: Path) -> Path:
    """Where the worktrees of the office on *project* (its main checkout) are kept."""
    return project.parent / f"{project.name}-worktrees"


def ticket_worktree(project: Path, ticket: str) -> Path:
    """The worktree of *ticket*: added the first time it is asked for, the same one from then on."""
    if Path(ticket).name != ticket:  # a ticket named like a path would land somewhere else
        raise ValueError(f"ticket {ticket!r} cannot name a worktree")
    path = worktrees_root(project) / f"ticket-{ticket}"
    with _adding:
        if not path.exists():
            # Told no branch, git makes the one named after the directory from the checkout's HEAD,
            # or checks out the one that a removed worktree left behind.
            added = subprocess.run(
                ["git", "-C", str(project), "worktree", "add", str(path)], capture_output=True, text=True
            )
            if added.returncode:
                raise RuntimeError(f"no worktree for ticket {ticket!r}: {added.stderr.strip()}")
    return path


def remove_finished_worktrees(project: Path, db_path: Path, gh: Gh) -> None:
    """Remove the worktree of each ticket whose pull request is merged or closed. Its branch stays.

    A worktree is kept while its ticket has an open pull request or none yet, or has a turn queued
    or running. Git keeps one that holds uncommitted work.
    """
    for path in worktrees_root(project).glob("ticket-*"):
        try:  # the ticket's pull requests are the ones from its branch
            found = json.loads(gh(["pr", "list", "--head", path.name, "--state", "all", "--json", "state"]))
        except (subprocess.CalledProcessError, OSError, ValueError):
            return  # gh did not answer; the next sweep asks again
        if not found or any(pr["state"] == "OPEN" for pr in found):
            continue
        # A turn queued from here on waits for the removal and adds the worktree again.
        # ponytail: that holds within the Session's server. A second `claudarama open` reviewing gates
        # while the office runs is another process; lock on a file if a turn ever loses its worktree to it.
        with _adding:
            if not ticket_has_turn(db_path, path.name.removeprefix("ticket-")):
                subprocess.run(["git", "-C", str(path), "worktree", "remove", str(path)], capture_output=True)
