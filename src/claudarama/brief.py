"""Brief builder: assembles a turn's brief from pack files on disk."""
from pathlib import Path

from claudarama.db import shown


def build_brief(
    pack_dir: Path,
    role: str,
    thread: list[dict] | None = None,
    ticket: str | None = None,
    working_note: str | None = None,
) -> str:
    """Build a brief from the pack's company.md and the role's profile file.

    Reads directly from disk so the latest merged changes are always reflected
    (spec requirement: no caching staleness).

    If *thread* is provided it is appended as a "## Message Thread" section so
    the receiver's fresh turn has full conversation context.
    """
    sections: list[str] = []

    # Company charter / goal
    company_path = pack_dir / "company.md"
    if company_path.is_file():
        sections.append(company_path.read_text(encoding="utf-8").strip())

    # Role / craft profile
    profile_path = pack_dir / "profiles" / f"{role}.md"
    if profile_path.is_file():
        sections.append(profile_path.read_text(encoding="utf-8").strip())

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

    return "\n\n---\n\n".join(sections) if sections else ""
