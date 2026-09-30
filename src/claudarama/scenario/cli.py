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


def discover_scenario_paths(explicit_paths: list[str]) -> list[Path]:
    """Resolve explicit paths or discover scenario files in standard locations."""
    if explicit_paths:
        resolved: list[Path] = []
        for p_str in explicit_paths:
            p = Path(p_str)
            if p.is_dir():
                resolved.extend(sorted(p.rglob("*.json")))
            else:
                resolved.append(p)
        return resolved

    # Auto-discovery in current project
    candidates = [
        Path(".claudarama/scenarios"),
        Path("scenarios"),
    ]
    discovered: list[Path] = []
    for cand in candidates:
        if cand.is_dir():
            discovered.extend(sorted(cand.rglob("*.json")))

    return discovered


def run_eval_cli(
    paths: list[str],
    runs: int = 1,
    against: Optional[str] = None,
    mock_response: Optional[str] = None,
) -> int:
    """CLI runner for evaluating scenarios."""
    from claudarama.scenario.runner import (
        MockInvoker,
        evaluate_against_ref,
        run_scenario_file,
    )

    if runs < 1:
        print(f"Error: --runs must be at least 1, got {runs}.", file=sys.stderr)
        return 1

    scenario_paths = discover_scenario_paths(paths)
    if not scenario_paths:
        print("Error: No scenario files found to evaluate.", file=sys.stderr)
        return 1

    invoker = MockInvoker(default_response=mock_response) if mock_response is not None else MockInvoker()

    if against:
        print(f"Comparing {len(scenario_paths)} scenario(s) against git ref '{against}' ({runs} run(s) per scenario)...")
        comp_summary = evaluate_against_ref(
            scenario_paths=scenario_paths,
            git_ref=against,
            invoker=invoker,
            runs=runs,
        )

        if comp_summary.error:
            print(f"Error: {comp_summary.error}", file=sys.stderr)
            return 1

        regressed_count = 0
        failed_count = 0
        passed_count = 0

        for cmp in comp_summary.comparisons:
            cur_status = "PASS" if cmp.current_result.passed else "FAIL"
            base_str = "N/A"
            if cmp.base_result is not None:
                base_status = "PASS" if cmp.base_result.passed else "FAIL"
                base_str = f"{base_status} ({cmp.base_result.passed_runs}/{cmp.base_result.total_runs} runs)"

            print(f"[{cmp.status}] {cmp.scenario_path.name}")
            print(f"  Current: {cur_status} ({cmp.current_result.passed_runs}/{cmp.current_result.total_runs} runs)")
            print(f"  Base:    {base_str}")

            if cmp.status == "REGRESSED":
                regressed_count += 1
                print(f"  WARNING: Performance regressed compared to {against}!", file=sys.stderr)

            if not cmp.current_result.passed:
                failed_count += 1
            else:
                passed_count += 1

        print(
            f"\nComparison against {against}: {passed_count} passed, {regressed_count} regressed, {failed_count} failed (Total: {len(scenario_paths)})"
        )
        return 0 if comp_summary.passed else 1

    print(f"Evaluating {len(scenario_paths)} scenario(s) ({runs} run(s) per scenario)...")
    passed_count = 0
    failed_count = 0

    for path in scenario_paths:
        res = run_scenario_file(path, invoker=invoker, runs=runs)
        if res.passed:
            passed_count += 1
            print(f"[PASS] {res.scenario_name} ({res.passed_runs}/{res.total_runs} runs passed)")
        else:
            failed_count += 1
            print(f"[FAIL] {res.scenario_name} ({res.passed_runs}/{res.total_runs} runs passed)")
            for err in res.validation_errors:
                print(f"  - Static validation error: {err}", file=sys.stderr)
            for err in res.self_test_errors:
                print(f"  - Excludes self-test error: {err}", file=sys.stderr)
            for idx, run in enumerate(res.run_results, 1):
                if not run.passed:
                    for msg in run.error_messages():
                        print(f"  - Run {idx}: {msg}", file=sys.stderr)

    print(f"\nResults: {passed_count} passed, {failed_count} failed (Total: {len(scenario_paths)})")
    return 0 if failed_count == 0 else 1

