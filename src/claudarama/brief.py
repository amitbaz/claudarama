"""Brief builder: assembles a turn's brief from the core's files and the pack's files on disk."""
from pathlib import Path

from claudarama.db import shown

CORE_DIR = Path(__file__).parent
ROLES_DIR = CORE_DIR / "roles"


# The seven fixed parts of a core role file, as its headings.
ROLE_FILE_PARTS = (
    "## What this Role is",
    "## Where it sits in the loop",
    "## What it produces",
    "## Who receives it",
    "## What done is backed by",
    "## What it leaves to others",
    "## When blocked or unclear",
)
ROLE_FILE_LINES = (40, 80)


def _read(path: Path) -> str | None:
    return path.read_text(encoding="utf-8").strip() if path.is_file() else None


def check_role_file(text: str) -> list[str]:
    """What is wrong with a core role file: a missing part, or a length outside the range."""
    lines = text.splitlines()
    problems = [f"missing part: {part}" for part in ROLE_FILE_PARTS if part not in lines]
    low, high = ROLE_FILE_LINES
    if not low <= len(lines) <= high:
        problems.append(f"{len(lines)} lines, outside {low} to {high}")
    return problems


def build_brief(
    pack_dir: Path,
    role: str,
    thread: list[dict] | None = None,
    ticket: str | None = None,
    working_note: str | None = None,
    lessons: list[str] | None = None,
) -> str:
    """Build a brief, most stable part first: charter, shared office rules, the Person's
    Role and name, core role file, pack overlay, Lessons in scope, the thread, the ticket,
    the working note.

    Reads directly from disk so the latest merged changes are always reflected
    (spec requirement: no caching staleness).
    """
    sections = [
        _read(pack_dir / "company.md"),
        _read(CORE_DIR / "office-rules.md"),
        f"You are the {shown(role)}.",
        _read(ROLES_DIR / f"{role}.md"),
        _read(pack_dir / "profiles" / f"{role}.md"),
    ]

    if lessons:
        sections.append("## Lessons\n\n" + "\n".join(f"- {lesson}" for lesson in lessons))

    # Message thread history (injected when replying to a message)
    if thread:
        lines = ["## Message Thread"]
        for msg in thread:
            sender = shown(msg.get("sender", "?"))
            receiver = shown(msg.get("receiver", "?"))
            msg_type = msg.get("msg_type", "")
            body = msg.get("body", "")
            lines.append(f"**{sender} → {receiver}** [{msg_type}]: {body}")
        sections.append("\n".join(lines))

    if ticket:
        sections.append(f"## Ticket\n\nWorking on ticket: {ticket}")

    if working_note:
        sections.append(f"## Working Note\n\n{working_note}")

    return "\n\n---\n\n".join(s for s in sections if s)
