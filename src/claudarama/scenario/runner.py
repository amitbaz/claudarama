"""Execution engine and runner for Claudarama scenario evaluation."""

from dataclasses import dataclass, field
import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Literal, Optional, Protocol, Sequence

from claudarama.scenario.judge import (
    CheckResult,
    JudgeResult,
    evaluate_excludes,
    evaluate_includes,
    parse_judge_output,
    self_test_all_excludes,
)
from claudarama.scenario.validator import (
    Scenario,
    validate_scenario,
    validate_scenario_file,
)

ComparisonStatus = Literal[
    "UNCHANGED",
    "IMPROVED",
    "REGRESSED",
    "STILL_FAILING",
    "NEW_PASS",
    "NEW_FAIL",
]


class LLMInvoker(Protocol):
    """Protocol for invoking an LLM or agent turn."""

    def invoke(self, prompt: str, scenario: Scenario) -> str:
        """Execute a prompt and return the text output."""
        ...


class MockInvoker:
    """Mock/stub LLM invoker for tests and offline validation."""

    def __init__(
        self,
        default_response: str = "Execution finished successfully.",
        responses: Optional[list[str]] = None,
        fn: Optional[Callable[[str, Scenario], str]] = None,
    ):
        self.default_response = default_response
        self._responses = list(responses) if responses else []
        self._fn = fn
        self.invocation_count = 0

    def invoke(self, prompt: str, scenario: Scenario) -> str:
        self.invocation_count += 1
        if self._fn is not None:
            return self._fn(prompt, scenario)
        if self._responses:
            return self._responses.pop(0)
        # Default judge response when evaluating judge prompt
        if "[Agent Output]:" in prompt or (scenario.judge and scenario.judge in prompt):
            return '{"pass": true, "reason": "Evaluated successfully"}'
        return self.default_response


@dataclass
class SingleRunResult:
    """Result of an individual execution run of a scenario."""

    passed: bool
    agent_reply: str
    include_checks: list[CheckResult] = field(default_factory=list)
    exclude_checks: list[CheckResult] = field(default_factory=list)
    judge_result: Optional[JudgeResult] = None
    error: Optional[str] = None

    def error_messages(self) -> list[str]:
        """Collect human-readable error messages for this run."""
        errs: list[str] = []
        for chk in self.include_checks:
            if not chk.passed:
                errs.append(f"Missing required pattern: {chk.pattern}")
        for chk in self.exclude_checks:
            if not chk.passed:
                errs.append(f"Matched excluded pattern: {chk.pattern}")
        if self.judge_result and not self.judge_result.passed:
            errs.append(f"Judge failed: {self.judge_result.reason}")
        if self.error:
            errs.append(self.error)
        return errs


@dataclass
class ScenarioEvaluationResult:
    """Aggregated evaluation result for a scenario across N runs."""

    scenario_name: str
    passed: bool
    total_runs: int
    passed_runs: int
    run_results: list[SingleRunResult] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    self_test_errors: list[str] = field(default_factory=list)


def evaluate_scenario(
    scenario: Scenario,
    invoker: Optional[LLMInvoker] = None,
    runs: int = 1,
) -> ScenarioEvaluationResult:
    """Evaluate a scenario definition using the provided invoker across N runs."""
    if runs < 1:
        raise ValueError(f"Number of runs must be at least 1, got {runs}.")

    if invoker is None:
        invoker = MockInvoker()

    # Step 1: Run self-test on all excludes patterns
    self_test_results = self_test_all_excludes(scenario.checks.excludes)
    failed_self_tests = [r.message for r in self_test_results if not r.passed]
    if failed_self_tests:
        return ScenarioEvaluationResult(
            scenario_name=scenario.name,
            passed=False,
            total_runs=runs,
            passed_runs=0,
            self_test_errors=failed_self_tests,
        )

    # Step 2: Execute runs
    run_results: list[SingleRunResult] = []
    passed_count = 0

    for _ in range(max(1, runs)):
        reply = invoker.invoke(scenario.prompt, scenario)

        # Evaluate checks
        inc_results = evaluate_includes(reply, scenario.checks.includes)
        exc_results = evaluate_excludes(reply, scenario.checks.excludes)

        inc_passed = all(r.passed for r in inc_results)
        exc_passed = all(r.passed for r in exc_results)

        judge_passed = True
        judge_res: Optional[JudgeResult] = None
        if scenario.judge:
            # Invoking judge with judge instructions and the agent reply to evaluate
            judge_prompt = f"{scenario.judge}\n\n[Agent Output]:\n{reply}"
            judge_raw = invoker.invoke(judge_prompt, scenario)
            judge_res = parse_judge_output(judge_raw)
            judge_passed = judge_res.passed

        run_passed = inc_passed and exc_passed and judge_passed
        if run_passed:
            passed_count += 1

        run_results.append(
            SingleRunResult(
                passed=run_passed,
                agent_reply=reply,
                include_checks=inc_results,
                exclude_checks=exc_results,
                judge_result=judge_res,
            )
        )

    # Majority pass requirement: strictly greater than half of total runs
    overall_passed = passed_count > (runs / 2)

    return ScenarioEvaluationResult(
        scenario_name=scenario.name,
        passed=overall_passed,
        total_runs=runs,
        passed_runs=passed_count,
        run_results=run_results,
    )


def run_scenario_file(
    file_path: str | Path,
    invoker: Optional[LLMInvoker] = None,
    runs: int = 1,
) -> ScenarioEvaluationResult:
    """Load, validate, and evaluate a scenario from a file."""
    path = Path(file_path)
    val_res = validate_scenario_file(path)
    if not val_res.valid or val_res.scenario is None:
        return ScenarioEvaluationResult(
            scenario_name=path.stem,
            passed=False,
            total_runs=runs,
            passed_runs=0,
            validation_errors=val_res.errors,
        )

    return evaluate_scenario(val_res.scenario, invoker=invoker, runs=runs)


@dataclass
class ScenarioComparison:
    """Comparison of a scenario's execution between current workspace and a base git ref."""

    scenario_path: Path
    current_result: ScenarioEvaluationResult
    base_result: Optional[ScenarioEvaluationResult]
    status: ComparisonStatus


@dataclass
class ComparisonSummary:
    """Summary of all scenario comparisons against a base git ref."""

    passed: bool
    git_ref: str
    comparisons: list[ScenarioComparison] = field(default_factory=list)
    error: Optional[str] = None


def load_scenario_from_git(
    repo_root: Path,
    git_ref: str,
    rel_path: str | Path,
) -> tuple[Optional[Scenario], list[str]]:
    """Load and validate a scenario file from a specific git ref."""
    try:
        proc = subprocess.run(
            ["git", "show", f"{git_ref}:{Path(rel_path).as_posix()}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        return None, [f"Failed to run git show for {rel_path} at {git_ref}: {exc}"]

    if proc.returncode != 0:
        return None, [f"File {rel_path} not found at {git_ref}"]

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return None, [f"Malformed JSON in {rel_path} at {git_ref}: {exc}"]

    val_res = validate_scenario(data)
    if not val_res.valid or val_res.scenario is None:
        return None, val_res.errors

    return val_res.scenario, []


def evaluate_against_ref(
    scenario_paths: Sequence[str | Path],
    git_ref: str,
    repo_root: Optional[Path] = None,
    invoker: Optional[LLMInvoker] = None,
    runs: int = 1,
) -> ComparisonSummary:
    """Evaluate scenarios on the current branch and compare performance against git_ref."""
    if runs < 1:
        raise ValueError(f"Number of runs must be at least 1, got {runs}.")

    if repo_root is None:
        repo_root = Path.cwd()

    # Verify that git_ref resolves
    verify_proc = subprocess.run(
        ["git", "rev-parse", "--verify", git_ref],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if verify_proc.returncode != 0:
        return ComparisonSummary(
            passed=False,
            git_ref=git_ref,
            comparisons=[],
            error=f"Invalid git reference: '{git_ref}'",
        )

    comparisons: list[ScenarioComparison] = []
    overall_passed = True

    for p in scenario_paths:
        path = Path(p).resolve()
        try:
            rel_path = path.relative_to(repo_root.resolve())
        except ValueError:
            rel_path = path

        current_res = run_scenario_file(path, invoker=invoker, runs=runs)

        # Base execution
        base_scenario, base_errs = load_scenario_from_git(repo_root, git_ref, rel_path)
        base_res: Optional[ScenarioEvaluationResult] = None

        if base_scenario is not None:
            base_res = evaluate_scenario(base_scenario, invoker=invoker, runs=runs)
        elif base_errs and "not found" not in base_errs[0].lower():
            # Error reading git ref
            base_res = ScenarioEvaluationResult(
                scenario_name=path.stem,
                passed=False,
                total_runs=runs,
                passed_runs=0,
                validation_errors=base_errs,
            )

        # Determine status
        status: ComparisonStatus
        if base_res is None:
            status = "NEW_PASS" if current_res.passed else "NEW_FAIL"
        else:
            if current_res.passed and base_res.passed:
                status = "UNCHANGED"
            elif current_res.passed and not base_res.passed:
                status = "IMPROVED"
            elif not current_res.passed and base_res.passed:
                status = "REGRESSED"
            else:
                status = "STILL_FAILING"

        if status == "REGRESSED" or not current_res.passed:
            overall_passed = False

        comparisons.append(
            ScenarioComparison(
                scenario_path=path,
                current_result=current_res,
                base_result=base_res,
                status=status,
            )
        )

    return ComparisonSummary(
        passed=overall_passed,
        git_ref=git_ref,
        comparisons=comparisons,
    )

