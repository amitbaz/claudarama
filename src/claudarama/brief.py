"""Brief builder: assembles a turn's brief from pack files on disk."""
from pathlib import Path


def build_brief(pack_dir: Path, role: str) -> str:
    """Build a brief from the pack's company.md and the role's profile file.

    Reads directly from disk so the latest merged changes are always reflected
    (spec requirement: no caching staleness).
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

    return "\n\n---\n\n".join(sections) if sections else ""
