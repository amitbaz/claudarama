"""A Diagnosis and a Retro are files in the project (spec #79, "Worktrees and documents").

Each lives in its own directory of the pack. Its author commits it on the branch of the mandate's
investigation ticket and opens a pull request from that branch. The CEO's YES at the Diagnosis gate
or the Lesson gate merges that pull request with no Ship-check: the CEO reads the document there.
"""
import json
import subprocess
from pathlib import Path, PurePosixPath

from claudarama.mirror import Gh
from claudarama.scaffold import PACK_DIR_NAME

DIAGNOSES = f"{PACK_DIR_NAME}/company/diagnoses"
RETROS = f"{PACK_DIR_NAME}/company/retros"


def document_path(path: str, directory: str, kind: str) -> str:
    """*path* as the office keeps it; refused unless it names a Markdown file in *directory*."""
    given = PurePosixPath(path)
    if given.parent != PurePosixPath(directory) or given.suffix != ".md":
        raise ValueError(f"a {kind} is accepted only at {directory}/<name>.md, from the project's root, not at {path!r}")
    return str(given)


def branch(ticket: str) -> str:
    """The branch of *ticket*'s worktree, where every turn on the ticket commits."""
    return f"ticket-{ticket}"


def committed(project: Path, ticket: str, path: str, kind: str) -> str:
    """The text of the document committed at *path* on *ticket*'s branch; refused when it is not there."""
    shown = subprocess.run(
        ["git", "-C", str(project), "show", f"{branch(ticket)}:{path}"], capture_output=True, text=True
    )
    if shown.returncode:
        raise ValueError(
            f"no {kind} is committed at {path} on the branch {branch(ticket)}: commit it there, then submit it again"
        )
    return shown.stdout


def missing_sections(diagnosis: str, judged_cases: bool) -> list[str]:
    """The required sections that *diagnosis* has no heading for. The judged cases are required
    only of a Diagnosis whose mandate has them."""
    required = ["Measure", "Rival explanations", *(["Judged cases"] if judged_cases else []), "Recommended strategy"]
    headings = [line.lower() for line in diagnosis.splitlines() if line.startswith("#")]
    # ponytail: a heading that names the section is all that is asked; what stands under it is for
    # the challenging Role and the CEO to judge.
    return [section for section in required if not any(section.lower() in heading for heading in headings)]


def open_pull_request(gh: Gh, ticket: str, kind: str) -> dict:
    """The open pull request from *ticket*'s branch, which holds its mandate's *kind*; refused when there is none."""
    found = json.loads(gh(["pr", "list", "--head", branch(ticket), "--state", "all", "--json", "number,state,headRefOid"]))
    for pr in found:
        if pr["state"] == "OPEN":
            return pr
    raise PermissionError(
        f"no open pull request from the branch {branch(ticket)} holds the {kind}, "
        "so the CEO's YES at its gate has nothing to merge"
    )
