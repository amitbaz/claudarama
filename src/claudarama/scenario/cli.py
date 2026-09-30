"""CLI interface for running the scenario free checker."""

from pathlib import Path
import sys
from typing import Optional

from claudarama.scenario.validator import validate_scenario_paths


def run_checker_cli(argv: Optional[list[str]] = None) -> int:
    """CLI runner for checking scenario files."""
    args = sys.argv[1:] if argv is None else argv

    if not args:
        print("Usage: python -m claudarama.scenario <scenario_file.json> ...", file=sys.stderr)
        return 1

    all_valid, results = validate_scenario_paths([Path(p) for p in args])

    for path_str, errors in results.items():
        if errors:
            print(f"FAILED: {path_str}", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
        else:
            print(f"PASSED: {path_str}")

    if not all_valid:
        print("\nFailed static validation: one or more scenario files are malformed.", file=sys.stderr)
        return 1

    print("\nPassed static validation: all scenario files are valid.")
    return 0
