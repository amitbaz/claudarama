import shutil
import subprocess
from pathlib import Path


DEFAULT_COMPANY_MD = """# Company Charter

## Mission
[Describe company charter and mission]

## Current Company Goal
[Describe current cycle goal]
"""

DEFAULT_ORG_YAML = """# Claudarama Org Configuration
concurrency: 3
stall_timeout_minutes: 20
"""

DEFAULT_GATES_YAML = """# Claudarama Gates Configuration
deny_rules:
  - "Bash(gh auth switch *)"
"""

DEFAULT_STACK_YAML = """# Claudarama Stack Configuration
# A Turn may run only the commands listed under commands, e.g.  test: "pytest"
commands:
"""

PACK_DIR_NAME = ".claudarama"

DEFAULT_FILES = {
    "company.md": DEFAULT_COMPANY_MD,
    "org.yaml": DEFAULT_ORG_YAML,
    "gates.yaml": DEFAULT_GATES_YAML,
    "stack.yaml": DEFAULT_STACK_YAML,
}

DEFAULT_DIRECTORIES = [
    "profiles",
    "scenarios",
    "company/diagnoses",
    "company/retros",
]


def gh_problem() -> str | None:
    """What to fix before the office can run, or None when `gh` is installed and signed in."""
    if shutil.which("gh") is None:
        return "gh (the GitHub CLI) is not installed. Install it from https://cli.github.com, then run setup again."
    if subprocess.run(["gh", "auth", "status"], capture_output=True).returncode != 0:
        return "gh is not signed in. Run `gh auth login`, then run setup again."
    return None


def setup_pack(target_path: Path | None = None) -> tuple[bool, str]:
    """Scaffold a default .claudarama/ pack in target_path (defaults to cwd)."""
    if problem := gh_problem():
        return False, problem
    base_path = target_path if target_path is not None else Path.cwd()
    pack_dir = base_path / PACK_DIR_NAME

    if pack_dir.exists():
        return True, f"Pack directory already exists: {pack_dir}"

    pack_dir.mkdir(parents=True, exist_ok=True)

    for subdir_rel in DEFAULT_DIRECTORIES:
        subdir = pack_dir / subdir_rel
        subdir.mkdir(parents=True, exist_ok=True)

    for filename, content in DEFAULT_FILES.items():
        file_path = pack_dir / filename
        file_path.write_text(content.strip() + "\n", encoding="utf-8")

    return True, f"Set up Claudarama pack in {pack_dir}"
