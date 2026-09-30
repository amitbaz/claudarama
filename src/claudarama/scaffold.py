from pathlib import Path


DEFAULT_COMPANY_MD = """# Company Charter

## Mission
[Describe company charter and mission]

## Current Company Goal
[Describe current cycle goal]
"""

DEFAULT_ORG_YAML = """# Claudarama Org Configuration
departments:
  leadership:
    open: true
    roles:
      - ceo
      - assistant
      - cto
      - cpo
  engineering:
    open: true
    roles:
      - engineering-lead
      - fullstack-engineer
      - frontend-engineer
      - database-architect
  product:
    open: true
    roles:
      - pm
  design:
    open: true
    roles:
      - designer
  ai:
    open: true
    roles:
      - prompt-engineer
      - eval-engineer
  research:
    open: true
    roles:
      - head-of-research
      - researcher
  marketing:
    open: false
    unlock_milestone: "first testers"
  support:
    open: false
    unlock_milestone: "first testers"
  finance_ops:
    open: false
    unlock_milestone: "first paid spend"

concurrency_cap:
  total: 7
  engineering: 3

stuck_turn_timeout_minutes: 20
"""

DEFAULT_GATES_YAML = """# Claudarama Gates Configuration
owner_only_actions:
  - money_and_spend
  - staging_and_production_deploys
  - hosted_databases
  - secrets_and_repo_settings
  - mandate_approval
  - direction_and_success_bar

spend_caps:
  ledger_turn_max_usd: 5.0
  ritual_sonnet_max_usd: 1.0
  review_opus_max_usd: 2.0

deny_rules:
  - "Bash(gh auth switch *)"
"""

DEFAULT_STACK_YAML = """# Claudarama Stack Configuration
checkout_path: "."
commands:
  test: "pytest"
  local_ci: "pytest"
migration_rules: []
stack_lock: false
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
    "plugins",
    "company/okrs",
    "company/all-hands",
    "company/retros",
    "company/reviews",
]


def init_pack(target_path: Path | None = None) -> tuple[bool, str]:
    """Scaffold a default .claudarama/ pack in target_path (defaults to cwd)."""
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

    return True, f"Initialized Claudarama pack in {pack_dir}"
