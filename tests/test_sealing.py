from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import pytest

from claudarama.scenario.validator import Scenario, ScenarioChecks
from claudarama.scenario.sealing import (
    SealingViolation,
    SealingResult,
    compare_scenario_constraints,
    compare_scenario_sets,
    load_scenarios_from_git,
    load_scenarios_from_directory,
    run_sealing_cli,
)


def make_scenario(
    name: str = "test-scenario",
    role: str = "fullstack-engineer",
    prompt: str = "Do work",
    description: str = "A test scenario",
    includes: list[str] | None = None,
    excludes: list[str] | None = None,
    judge: str | None = None,
) -> Scenario:
    return Scenario(
        name=name,
        role=role,
        prompt=prompt,
        description=description,
        checks=ScenarioChecks(
            includes=includes or [],
            excludes=excludes or [],
        ),
        judge=judge,
    )


def test_compare_scenario_constraints_identical():
    s1 = make_scenario(includes=["PASS"], excludes=[r"\bpkill\b"], judge="Check output")
    s2 = make_scenario(includes=["PASS"], excludes=[r"\bpkill\b"], judge="Check output")

    violations = compare_scenario_constraints(s1, s2, "scenarios/s.json")
    assert violations == []


def test_compare_scenario_constraints_tightened():
    base = make_scenario(includes=["PASS"], excludes=[r"\bpkill\b"], judge=None)
    # Current adds more assertions and a judge
    curr = make_scenario(
        includes=["PASS", "READY"],
        excludes=[r"\bpkill\b", r"\bkillall\b"],
        judge="Strict judge",
    )

    violations = compare_scenario_constraints(base, curr, "scenarios/s.json")
    assert violations == []


def test_compare_scenario_constraints_loosened_includes():
    base = make_scenario(includes=["PASS", "OK"])
    curr = make_scenario(includes=["PASS"])

    violations = compare_scenario_constraints(base, curr, "scenarios/s.json")
    assert len(violations) == 1
    assert "Missing required 'includes' assertions: ['OK']" in violations[0].message


def test_compare_scenario_constraints_loosened_excludes():
    base = make_scenario(excludes=[r"\bpkill\b", r"\bkillall\b"])
    curr = make_scenario(excludes=[r"\bpkill\b"])

    violations = compare_scenario_constraints(base, curr, "scenarios/s.json")
    assert len(violations) == 1
    assert "Missing required 'excludes' assertions" in violations[0].message
    assert "killall" in violations[0].message


def test_compare_scenario_constraints_judge_removed():
    base = make_scenario(judge="Must check assertions")
    curr = make_scenario(judge=None)

    violations = compare_scenario_constraints(base, curr, "scenarios/s.json")
    assert len(violations) == 1
    assert "judge was removed" in violations[0].message


def test_compare_scenario_constraints_judge_improved_allowed():
    base = make_scenario(judge="Must check assertions")
    curr = make_scenario(judge="Must check assertions with stricter adherence")

    violations = compare_scenario_constraints(base, curr, "scenarios/s.json")
    assert violations == []


def test_compare_scenario_constraints_prompt_altered():
    base = make_scenario(prompt="Strict prompt")
    curr = make_scenario(prompt="Easy prompt")

    violations = compare_scenario_constraints(base, curr, "scenarios/s.json")
    assert len(violations) == 1
    assert "prompt was altered" in violations[0].message


def test_compare_scenario_constraints_role_altered():
    base = make_scenario(role="fullstack-engineer")
    curr = make_scenario(role="pm")

    violations = compare_scenario_constraints(base, curr, "scenarios/s.json")
    assert len(violations) == 1
    assert "Role changed from 'fullstack-engineer' to 'pm'" in violations[0].message



def test_compare_scenario_sets_deleted_file():
    base_scenarios = {"scenarios/s1.json": make_scenario(name="s1")}
    current_scenarios = {}

    result = compare_scenario_sets(base_scenarios, current_scenarios)
    assert result.sealed is False
    assert len(result.violations) == 1
    assert "was deleted" in result.violations[0].message


def test_compare_scenario_sets_renamed_file_same_name_allowed():
    base_scenarios = {"scenarios/old_path.json": make_scenario(name="s1", includes=["PASS"])}
    current_scenarios = {"scenarios/new_path.json": make_scenario(name="s1", includes=["PASS"])}

    result = compare_scenario_sets(base_scenarios, current_scenarios)
    assert result.sealed is True
    assert result.violations == []


def test_compare_scenario_sets_new_scenario_allowed():
    base_scenarios = {"scenarios/s1.json": make_scenario(name="s1")}
    current_scenarios = {
        "scenarios/s1.json": make_scenario(name="s1"),
        "scenarios/s2.json": make_scenario(name="s2"),
    }

    result = compare_scenario_sets(base_scenarios, current_scenarios)
    assert result.sealed is True
    assert result.violations == []
    assert result.base_count == 1
    assert result.current_count == 2



@pytest.fixture
def git_repo(tmp_path: Path):
    """Set up a temporary git repository with a committed scenario."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)

    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    scenario_file = scenarios_dir / "test.json"
    scenario_file.write_text(
        json.dumps({
            "name": "base-test",
            "role": "fullstack-engineer",
            "prompt": "Run benchmark",
            "checks": {
                "includes": ["PASS"],
                "excludes": [r"\bpkill\b"],
            },
        }),
        encoding="utf-8",
    )

    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial scenario"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def test_sealing_git_lifecycle(git_repo: Path, capsys):
    # 1. Unchanged -> Sealed
    exit_code = run_sealing_cli(["--base", "HEAD", "--dir", "scenarios", "--cwd", str(git_repo)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "PASSED:" in captured.out

    # 2. Add tighter checks -> Sealed
    scenario_file = git_repo / "scenarios" / "test.json"
    scenario_file.write_text(
        json.dumps({
            "name": "base-test",
            "role": "fullstack-engineer",
            "prompt": "Run benchmark",
            "checks": {
                "includes": ["PASS", "EXTRA_PASS"],
                "excludes": [r"\bpkill\b", r"\bkillall\b"],
            },
        }),
        encoding="utf-8",
    )
    exit_code = run_sealing_cli(["--base", "HEAD", "--dir", "scenarios", "--cwd", str(git_repo)])
    assert exit_code == 0
    capsys.readouterr()

    # 3. Loosen checks (remove PASS) -> Fails
    scenario_file.write_text(
        json.dumps({
            "name": "base-test",
            "role": "fullstack-engineer",
            "prompt": "Run benchmark",
            "checks": {
                "excludes": [r"\bpkill\b"],
            },
        }),
        encoding="utf-8",
    )
    exit_code = run_sealing_cli(["--base", "HEAD", "--dir", "scenarios", "--cwd", str(git_repo)])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "FAILED:" in captured.err
    assert "Missing required 'includes' assertions" in captured.err

    # 4. Loosened checks with --allow-loosened -> Returns 0
    exit_code = run_sealing_cli(["--base", "HEAD", "--dir", "scenarios", "--allow-loosened", "--cwd", str(git_repo)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "WARNING: Violations detected but --allow-loosened was passed" in captured.err


    # 5. Delete scenario -> Fails
    scenario_file.unlink()
    exit_code = run_sealing_cli(["--base", "HEAD", "--dir", "scenarios", "--cwd", str(git_repo)])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "was deleted" in captured.err



def test_sealing_invalid_base_ref(git_repo: Path, capsys):
    exit_code = run_sealing_cli(["--base", "invalid_ref_12345", "--dir", "scenarios", "--cwd", str(git_repo)])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Error:" in captured.err
