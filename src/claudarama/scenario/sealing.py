"""Scenario constraint sealing checker against base git ref."""

import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Optional, Sequence

from claudarama.scenario.validator import (
    Scenario,
    validate_scenario,
    validate_scenario_file,
)


@dataclass
class SealingViolation:
    file_path: str
    scenario_name: str
    message: str


@dataclass
class SealingResult:
    sealed: bool
    violations: list[SealingViolation] = field(default_factory=list)
    base_count: int = 0
    current_count: int = 0


def _check_missing_patterns(
    base_patterns: list[str],
    current_patterns: list[str],
    pattern_type: str,
    file_path: str,
    scenario_name: str,
) -> Optional[SealingViolation]:
    """Check if any required assertion patterns from base are missing in current."""
    missing = sorted(set(base_patterns) - set(current_patterns))
    if missing:
        formatted = ", ".join(f"'{item}'" for item in missing)
        return SealingViolation(
            file_path=file_path,
            scenario_name=scenario_name,
            message=f"Missing required '{pattern_type}' assertions: [{formatted}]",
        )
    return None


def compare_scenario_constraints(
    base: Scenario,
    current: Scenario,
    file_path: str,
) -> list[SealingViolation]:
    """Compare base and current scenario definitions.

    Returns a list of violations if current scenario loosened any constraints.
    """
    violations: list[SealingViolation] = []

    # Scenario role cannot be changed
    if base.role != current.role:
        violations.append(
            SealingViolation(
                file_path=file_path,
                scenario_name=base.name,
                message=f"Role changed from '{base.role}' to '{current.role}'.",
            )
        )

    # Prompt cannot be altered
    if base.prompt != current.prompt:
        violations.append(
            SealingViolation(
                file_path=file_path,
                scenario_name=base.name,
                message="Scenario prompt was altered.",
            )
        )

    # All base 'includes' must still be present in current
    v_inc = _check_missing_patterns(
        base.checks.includes,
        current.checks.includes,
        "includes",
        file_path,
        base.name,
    )
    if v_inc:
        violations.append(v_inc)

    # All base 'excludes' must still be present in current
    v_exc = _check_missing_patterns(
        base.checks.excludes,
        current.checks.excludes,
        "excludes",
        file_path,
        base.name,
    )
    if v_exc:
        violations.append(v_exc)

    # Judge: if base had a judge, current must not remove it
    if base.judge and base.judge.strip():
        if not current.judge or not current.judge.strip():
            violations.append(
                SealingViolation(
                    file_path=file_path,
                    scenario_name=base.name,
                    message="Scenario judge was removed.",
                )
            )

    return violations


def compare_scenario_sets(
    base_scenarios: dict[str, Scenario],
    current_scenarios: dict[str, Scenario],
) -> SealingResult:
    """Compare a collection of base scenarios against current scenarios.

    Matching is done primarily by scenario name, falling back to file path.
    """
    violations: list[SealingViolation] = []

    # Index current scenarios by name and by path
    current_by_name: dict[str, tuple[str, Scenario]] = {}
    current_by_path: dict[str, Scenario] = {}
    for path, sc in current_scenarios.items():
        current_by_name[sc.name] = (path, sc)
        current_by_path[path] = sc

    for path, base_sc in base_scenarios.items():
        matched_sc: Optional[Scenario] = None
        matched_path: str = path

        if base_sc.name in current_by_name:
            matched_path, matched_sc = current_by_name[base_sc.name]
        elif path in current_by_path:
            matched_sc = current_by_path[path]

        if matched_sc is None:
            violations.append(
                SealingViolation(
                    file_path=path,
                    scenario_name=base_sc.name,
                    message=f"Scenario '{base_sc.name}' ({path}) was deleted.",
                )
            )
        else:
            violations.extend(compare_scenario_constraints(base_sc, matched_sc, matched_path))

    return SealingResult(
        sealed=(len(violations) == 0),
        violations=violations,
        base_count=len(base_scenarios),
        current_count=len(current_scenarios),
    )


def git_ref_exists(ref: str, cwd: Optional[Path] = None) -> bool:
    """Check if a git ref resolves to a valid object."""
    res = subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        cwd=cwd,
        capture_output=True,
        check=False,
    )
    return res.returncode == 0


def resolve_git_ref(ref: str, cwd: Optional[Path] = None) -> str:
    """Resolve a git ref, trying fallback without remote prefix if needed."""
    if git_ref_exists(ref, cwd=cwd):
        return ref
    # If ref is origin/foo, try foo
    if ref.startswith("origin/"):
        fallback = ref[len("origin/"):]
        if git_ref_exists(fallback, cwd=cwd):
            return fallback
    raise ValueError(f"Git ref '{ref}' could not be resolved in the repository.")


def load_scenarios_from_git(
    ref: str,
    scenarios_dir: str = "scenarios",
    cwd: Optional[Path] = None,
) -> dict[str, Scenario]:
    """Load and validate all scenario JSON files at a git ref."""
    resolved_ref = resolve_git_ref(ref, cwd=cwd)

    # List files under scenarios_dir at git ref
    cmd = ["git", "ls-tree", "-r", "--name-only", resolved_ref, "--", scenarios_dir]
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return {}

    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    json_paths = [p for p in lines if p.endswith(".json")]

    scenarios: dict[str, Scenario] = {}
    for p in json_paths:
        cat_cmd = ["git", "show", f"{resolved_ref}:{p}"]
        cat_proc = subprocess.run(cat_cmd, cwd=cwd, capture_output=True, text=True, check=False)
        if cat_proc.returncode != 0:
            continue
        try:
            data = json.loads(cat_proc.stdout)
        except json.JSONDecodeError:
            continue
        res = validate_scenario(data)
        if res.valid and res.scenario is not None:
            scenarios[p] = res.scenario

    return scenarios


def load_scenarios_from_directory(
    scenarios_dir: str | Path = "scenarios",
    cwd: Optional[Path] = None,
) -> dict[str, Scenario]:
    """Load and validate all scenario JSON files from directory in filesystem."""
    root = (cwd or Path.cwd()).resolve()
    target_dir = root / scenarios_dir
    if not target_dir.is_dir():
        return {}

    scenarios: dict[str, Scenario] = {}
    for path in sorted(target_dir.glob("**/*.json")):
        res = validate_scenario_file(path)
        if not res.valid or res.scenario is None:
            raise ValueError(f"Scenario file '{path}' is invalid: {'; '.join(res.errors)}")
        rel_path = str(path.relative_to(root))
        scenarios[rel_path] = res.scenario

    return scenarios


def resolve_default_base_ref(cwd: Optional[Path] = None) -> str:
    """Determine the default git base ref to compare against."""
    # 1. If GITHUB_BASE_REF is set (in GitHub Actions PR)
    env_base = os.environ.get("GITHUB_BASE_REF")
    if env_base:
        if git_ref_exists(f"origin/{env_base}", cwd=cwd):
            return f"origin/{env_base}"
        if git_ref_exists(env_base, cwd=cwd):
            return env_base

    # 2. Check origin/main, then main
    if git_ref_exists("origin/main", cwd=cwd):
        return "origin/main"
    if git_ref_exists("main", cwd=cwd):
        return "main"

    return "HEAD~1"


def run_sealing_cli(argv: Optional[Sequence[str]] = None) -> int:
    """CLI runner for scenario constraint sealing checks."""
    parser = argparse.ArgumentParser(
        prog="check_sealing",
        description="Verify scenario constraints have not been loosened compared to base branch.",
    )
    parser.add_argument(
        "--base",
        dest="base_ref",
        help="Git ref of the base branch to compare against (e.g. origin/main)",
    )
    parser.add_argument(
        "--dir",
        dest="scenarios_dir",
        default="scenarios",
        help="Directory containing scenario files (default: scenarios)",
    )
    parser.add_argument(
        "--allow-loosened",
        action="store_true",
        help="Emergency override: warn but do not fail if constraints are loosened",
    )
    parser.add_argument(
        "--cwd",
        dest="cwd",
        default=None,
        help=argparse.SUPPRESS,  # Internal test flag to target specific directory
    )
    args = parser.parse_args(argv)

    target_cwd = Path(args.cwd) if args.cwd else None
    base_ref = args.base_ref or resolve_default_base_ref(cwd=target_cwd)

    try:
        base_scenarios = load_scenarios_from_git(
            base_ref,
            scenarios_dir=args.scenarios_dir,
            cwd=target_cwd,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        current_scenarios = load_scenarios_from_directory(
            scenarios_dir=args.scenarios_dir,
            cwd=target_cwd,
        )
    except Exception as exc:
        print(f"Error loading current scenarios: {exc}", file=sys.stderr)
        return 1

    result = compare_scenario_sets(base_scenarios, current_scenarios)

    if not result.sealed:
        print(
            f"FAILED: Scenario sealing check failed against base '{base_ref}':",
            file=sys.stderr,
        )
        for v in result.violations:
            print(f"  [{v.file_path}] {v.message}", file=sys.stderr)

        if args.allow_loosened:
            print(
                "WARNING: Violations detected but --allow-loosened was passed. Proceeding.",
                file=sys.stderr,
            )
            return 0
        return 1

    print(
        f"PASSED: Scenario sealing check passed ({result.base_count} base scenarios verified against '{base_ref}')."
    )
    return 0


if __name__ == "__main__":
    sys.exit(run_sealing_cli())
