"""Tests for scenario harness execution engine and runner."""

from pathlib import Path
from claudarama.scenario.validator import Scenario, ScenarioChecks
from claudarama.scenario.runner import evaluate_scenario, MockInvoker, run_scenario_file


def test_evaluate_scenario_passes_when_includes_and_excludes_satisfied():
    scenario = Scenario(
        name="test-pass",
        role="engineer",
        prompt="Do the job",
        checks=ScenarioChecks(includes=["SUCCESS"], excludes=["ERROR"]),
    )
    invoker = MockInvoker(default_response="SUCCESS: all steps completed")
    result = evaluate_scenario(scenario, invoker=invoker, runs=1)

    assert result.passed is True
    assert result.total_turns == 1
    assert result.passed_turns == 1
    assert len(result.turn_results) == 1
    assert result.turn_results[0].passed is True


def test_evaluate_scenario_fails_when_excludes_matched():
    scenario = Scenario(
        name="test-fail-exclude",
        role="engineer",
        prompt="Do the job",
        checks=ScenarioChecks(includes=["SUCCESS"], excludes=["ERROR"]),
    )
    invoker = MockInvoker(default_response="SUCCESS but with ERROR in log")
    result = evaluate_scenario(scenario, invoker=invoker, runs=1)

    assert result.passed is False
    assert result.total_turns == 1
    assert result.passed_turns == 0
    assert result.turn_results[0].passed is False


def test_run_scenario_file_fails_free_checker_without_invoking_llm(tmp_path: Path):
    invalid_file = tmp_path / "bad.json"
    invalid_file.write_text('{"name": "bad", "role": "eng"}')  # Missing prompt and checks

    invoker = MockInvoker()
    result = run_scenario_file(invalid_file, invoker=invoker, runs=1)

    assert result.passed is False
    assert len(result.validation_errors) > 0
    assert invoker.invocation_count == 0


def test_evaluate_scenario_fails_on_excludes_self_test_without_invoking_llm():
    # An invalid regex pattern causes evaluate_exclude_pattern to error, failing self-test
    scenario = Scenario(
        name="test-invalid-regex",
        role="engineer",
        prompt="Do the job",
        checks=ScenarioChecks(excludes=["[unclosed"]),
    )
    invoker = MockInvoker()
    result = evaluate_scenario(scenario, invoker=invoker, runs=1)

    assert result.passed is False
    assert len(result.self_test_errors) > 0
    assert invoker.invocation_count == 0


def test_evaluate_scenario_with_strict_json_judge_pass():
    scenario = Scenario(
        name="judge-test",
        role="engineer",
        prompt="Write a function",
        judge="Judge if the function is correct",
    )
    # First invoke returns agent reply, second invoke returns judge JSON
    invoker = MockInvoker(responses=[
        "def add(a, b): return a + b",
        '{"pass": true, "reason": "Function is correct"}',
    ])
    result = evaluate_scenario(scenario, invoker=invoker, runs=1)

    assert result.passed is True
    assert result.turn_results[0].judge_result is not None
    assert result.turn_results[0].judge_result.passed is True
    assert result.turn_results[0].judge_result.reason == "Function is correct"


def test_evaluate_scenario_with_strict_json_judge_fail_and_malformed():
    scenario = Scenario(
        name="judge-malformed",
        role="engineer",
        prompt="Write a function",
        judge="Judge if the function is correct",
    )
    invoker = MockInvoker(responses=[
        "def add(a, b): return a + b",
        "It looks good to me! (Not valid JSON)",
    ])
    result = evaluate_scenario(scenario, invoker=invoker, runs=1)

    assert result.passed is False
    assert result.turn_results[0].judge_result is not None
    assert result.turn_results[0].judge_result.passed is False
    assert "Malformed JSON" in result.turn_results[0].judge_result.reason


def test_runs_majority_rule_passes_on_two_out_of_three():
    scenario = Scenario(
        name="majority-pass",
        role="engineer",
        prompt="Do the job",
        checks=ScenarioChecks(includes=["OK"]),
    )
    # 2 passes, 1 failure
    invoker = MockInvoker(responses=["OK", "NOPE", "OK"])
    result = evaluate_scenario(scenario, invoker=invoker, runs=3)

    assert result.passed is True
    assert result.total_turns == 3
    assert result.passed_turns == 2
    assert len(result.turn_results) == 3


def test_runs_majority_rule_fails_on_one_out_of_three():
    scenario = Scenario(
        name="majority-fail",
        role="engineer",
        prompt="Do the job",
        checks=ScenarioChecks(includes=["OK"]),
    )
    # 1 pass, 2 failures
    invoker = MockInvoker(responses=["OK", "NOPE", "NOPE"])
    result = evaluate_scenario(scenario, invoker=invoker, runs=3)

    assert result.passed is False
    assert result.total_turns == 3
    assert result.passed_turns == 1
    assert len(result.turn_results) == 3


def test_evaluate_against_ref_detects_improvements_and_regressions(tmp_path: Path):
    import subprocess
    from claudarama.scenario.runner import evaluate_against_ref

    # Initialize a temporary git repository
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=tmp_path, check=True)

    # Base commit with scenario expecting "OLD_TOKEN"
    scenario_path = tmp_path / "scenario.json"
    scenario_path.write_text('{"name": "test-scenario", "role": "eng", "prompt": "run", "checks": {"includes": ["OLD_TOKEN"]}}')
    subprocess.run(["git", "add", "scenario.json"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "base commit"], cwd=tmp_path, check=True)
    base_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()

    # Current worktree updates scenario to expect "NEW_TOKEN"
    scenario_path.write_text('{"name": "test-scenario", "role": "eng", "prompt": "run", "checks": {"includes": ["NEW_TOKEN"]}}')

    # Invoker that outputs "NEW_TOKEN"
    invoker = MockInvoker(default_response="Output with NEW_TOKEN here")
    comp_result = evaluate_against_ref(
        scenario_paths=[scenario_path],
        git_ref=base_commit,
        repo_root=tmp_path,
        invoker=invoker,
        runs=1,
    )

    assert comp_result.passed is True
    assert len(comp_result.comparisons) == 1
    cmp = comp_result.comparisons[0]
    assert cmp.current_result.passed is True
    assert cmp.base_result is not None
    assert cmp.base_result.passed is False
    assert cmp.status == "IMPROVED"


def test_evaluate_against_ref_detects_regression(tmp_path: Path):
    import subprocess
    from claudarama.scenario.runner import evaluate_against_ref

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=tmp_path, check=True)

    # Base commit with scenario expecting "SUCCESS"
    scenario_path = tmp_path / "scenario.json"
    scenario_path.write_text('{"name": "test-scenario", "role": "eng", "prompt": "run", "checks": {"includes": ["SUCCESS"]}}')
    subprocess.run(["git", "add", "scenario.json"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "base commit"], cwd=tmp_path, check=True)
    base_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()

    # Current worktree updates scenario to expect "IMPOSSIBLE" which our invoker won't produce
    scenario_path.write_text('{"name": "test-scenario", "role": "eng", "prompt": "run", "checks": {"includes": ["IMPOSSIBLE"]}}')

    # Invoker that outputs "SUCCESS"
    invoker = MockInvoker(default_response="Output with SUCCESS")
    comp_result = evaluate_against_ref(
        scenario_paths=[scenario_path],
        git_ref=base_commit,
        repo_root=tmp_path,
        invoker=invoker,
        runs=1,
    )

    assert comp_result.passed is False
    assert len(comp_result.comparisons) == 1
    cmp = comp_result.comparisons[0]
    assert cmp.current_result.passed is False
    assert cmp.base_result is not None
    assert cmp.base_result.passed is True
    assert cmp.status == "REGRESSED"





