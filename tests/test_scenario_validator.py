from pathlib import Path
import json
import pytest

from claudarama.scenario import (
    Scenario,
    ScenarioChecks,
    ScenarioValidationError,
    ValidationResult,
    load_scenario,
    run_checker_cli,
    validate_scenario,
    validate_scenario_file,
    validate_scenario_paths,
)


def test_validate_scenario_valid_dict():
    data = {
        "name": "pm-flags-ambiguity",
        "description": "PM flags ambiguous criterion to CPO",
        "role": "pm",
        "prompt": "Evaluate this ticket for ambiguity",
        "checks": {
            "includes": ["AMBIGUOUS:"],
            "excludes": [r"\bpkill\b"],
        },
        "judge": "Verify the agent spotted the ambiguity.",
    }
    result = validate_scenario(data)
    assert result.valid is True
    assert result.errors == []
    assert isinstance(result.scenario, Scenario)
    assert result.scenario.name == "pm-flags-ambiguity"
    assert result.scenario.role == "pm"
    assert result.scenario.prompt == "Evaluate this ticket for ambiguity"
    assert result.scenario.checks.includes == ["AMBIGUOUS:"]
    assert result.scenario.checks.excludes == [r"\bpkill\b"]
    assert result.scenario.judge == "Verify the agent spotted the ambiguity."


def test_validate_scenario_file_valid(tmp_path: Path):
    scenario_path = tmp_path / "valid_scenario.json"
    scenario_path.write_text(
        json.dumps({
            "name": "fullstack-tests-pass",
            "role": "fullstack-engineer",
            "prompt": "Run tests and verify output",
            "checks": {
                "includes": ["PASS"],
            },
        }),
        encoding="utf-8",
    )
    result = validate_scenario_file(scenario_path)
    assert result.valid is True
    assert result.errors == []
    assert result.scenario is not None
    assert result.scenario.name == "fullstack-tests-pass"
    assert result.scenario.role == "fullstack-engineer"

    loaded = load_scenario(scenario_path)
    assert loaded.name == "fullstack-tests-pass"


def test_validate_scenario_file_not_found(tmp_path: Path):
    non_existent = tmp_path / "missing.json"
    result = validate_scenario_file(non_existent)
    assert result.valid is False
    assert any("not found" in err.lower() for err in result.errors)

    with pytest.raises(ScenarioValidationError) as exc_info:
        load_scenario(non_existent)
    assert any("not found" in err.lower() for err in exc_info.value.errors)


def test_validate_scenario_file_malformed_json(tmp_path: Path):
    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text('{"name": "broken", "role": "cpo", ', encoding="utf-8")

    result = validate_scenario_file(malformed_path)
    assert result.valid is False
    assert any("malformed json" in err.lower() for err in result.errors)

    with pytest.raises(ScenarioValidationError) as exc_info:
        load_scenario(malformed_path)
    assert any("malformed json" in err.lower() for err in exc_info.value.errors)


def test_validate_scenario_file_schema_violations_on_disk(tmp_path: Path):
    invalid_schema_path = tmp_path / "invalid_schema.json"
    invalid_schema_path.write_text(
        json.dumps({
            "name": "typo-role",
            "roel": "fullstack-engineer",  # typo
            "prompt": 12345,  # wrong type
        }),
        encoding="utf-8",
    )
    result = validate_scenario_file(invalid_schema_path)
    assert result.valid is False
    assert any("Unrecognized fields in scenario: roel" in err for err in result.errors)
    assert any("Field 'role' is required" in err for err in result.errors)
    assert any("Field 'prompt' is required" in err for err in result.errors)

    with pytest.raises(ScenarioValidationError):
        load_scenario(invalid_schema_path)


def test_validate_scenario_not_a_dict():
    result = validate_scenario(["not", "a", "dict"])
    assert result.valid is False
    assert "must be a JSON object" in result.errors[0]


def test_validate_scenario_missing_required_fields():
    result = validate_scenario({})
    assert result.valid is False
    assert any("Field 'name' is required" in err for err in result.errors)
    assert any("Field 'role' is required" in err for err in result.errors)
    assert any("Field 'prompt' is required" in err for err in result.errors)


def test_validate_scenario_empty_or_wrong_type_required_fields():
    data = {
        "name": "   ",
        "role": 123,
        "prompt": None,
        "description": 456,
        "checks": "not-a-dict",
        "judge": 789,
    }
    result = validate_scenario(data)
    assert result.valid is False
    assert any("Field 'name' is required and must be a non-empty string." in err for err in result.errors)
    assert any("Field 'role' is required and must be a non-empty string." in err for err in result.errors)
    assert any("Field 'prompt' is required and must be a non-empty string." in err for err in result.errors)
    assert any("Field 'description' must be a string" in err for err in result.errors)
    assert any("Field 'checks' must be an object" in err for err in result.errors)
    assert any("Field 'judge' must be a non-empty string" in err for err in result.errors)


def test_validate_scenario_unrecognized_keys():
    data = {
        "name": "extra-keys",
        "role": "pm",
        "prompt": "Evaluate",
        "extra_field": "disallowed",
        "checks": {
            "includes": ["ok"],
            "extra_check": "disallowed",
        },
    }
    result = validate_scenario(data)
    assert result.valid is False
    assert any("Unrecognized fields in scenario: extra_field" in err for err in result.errors)
    assert any("Unrecognized fields in 'checks': extra_check" in err for err in result.errors)


def test_validate_scenario_no_assertions():
    data = {
        "name": "no-checks",
        "role": "pm",
        "prompt": "Do nothing",
    }
    result = validate_scenario(data)
    assert result.valid is False
    assert any("Scenario must declare at least one check" in err for err in result.errors)


def test_validate_scenario_invalid_regex_patterns():
    data = {
        "name": "bad-regex",
        "role": "lead",
        "prompt": "Check code",
        "checks": {
            "includes": ["[unclosed-bracket"],
            "excludes": ["*invalid-regex+"],
        },
    }
    result = validate_scenario(data)
    assert result.valid is False
    assert any("Invalid regex in 'checks.includes'" in err for err in result.errors)
    assert any("Invalid regex in 'checks.excludes'" in err for err in result.errors)


def test_validate_scenario_invalid_checks_list_elements():
    data = {
        "name": "bad-items",
        "role": "lead",
        "prompt": "Check code",
        "checks": {
            "includes": ["valid", 123, "", "   "],
            "excludes": [None],
        },
    }
    result = validate_scenario(data)
    assert result.valid is False
    assert any("'checks.includes' must be a list of non-empty strings" in err for err in result.errors)
    assert any("'checks.excludes' must be a list of non-empty strings" in err for err in result.errors)


def test_validate_scenario_only_judge():
    data = {
        "name": "judge-only",
        "role": "cto",
        "prompt": "Review architecture",
        "judge": "Return pass if the architecture has proper seams.",
    }
    result = validate_scenario(data)
    assert result.valid is True
    assert result.errors == []
    assert result.scenario is not None
    assert result.scenario.judge == "Return pass if the architecture has proper seams."
    assert result.scenario.checks.includes == []
    assert result.scenario.checks.excludes == []


def test_validate_scenario_only_excludes():
    data = {
        "name": "no-pkill",
        "role": "fullstack-engineer",
        "prompt": "Never kill processes",
        "checks": {
            "excludes": [r"\bpkill\b"],
        },
    }
    result = validate_scenario(data)
    assert result.valid is True
    assert result.scenario is not None
    assert result.scenario.checks.excludes == [r"\bpkill\b"]


def test_validate_scenario_paths_all_valid(tmp_path: Path):
    s1 = tmp_path / "s1.json"
    s1.write_text(json.dumps({"name": "s1", "role": "cpo", "prompt": "p1", "judge": "j1"}))

    s2 = tmp_path / "s2.json"
    s2.write_text(json.dumps({"name": "s2", "role": "cto", "prompt": "p2", "checks": {"includes": ["ok"]}}))

    all_valid, results = validate_scenario_paths([s1, s2])
    assert all_valid is True
    assert len(results) == 2
    assert results[str(s1)] == []
    assert results[str(s2)] == []


def test_validate_scenario_paths_with_failures(tmp_path: Path):
    s_good = tmp_path / "good.json"
    s_good.write_text(json.dumps({"name": "good", "role": "pm", "prompt": "p", "judge": "j"}))

    s_bad = tmp_path / "bad.json"
    s_bad.write_text(json.dumps({"name": "bad", "role": 123, "prompt": ""}))

    all_valid, results = validate_scenario_paths([s_good, s_bad])
    assert all_valid is False
    assert results[str(s_good)] == []
    assert len(results[str(s_bad)]) > 0


def test_runner_cli_success(tmp_path: Path, capsys):
    s = tmp_path / "valid.json"
    s.write_text(json.dumps({"name": "s", "role": "pm", "prompt": "p", "judge": "j"}))

    exit_code = run_checker_cli([str(s)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Passed static validation" in captured.out


def test_runner_cli_failure(tmp_path: Path, capsys):
    s = tmp_path / "invalid.json"
    s.write_text('{"name": "broken", ')

    exit_code = run_checker_cli([str(s)])
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "Failed static validation" in captured.err or "Malformed JSON" in captured.err


def test_runner_cli_no_args(capsys):
    exit_code = run_checker_cli([])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Usage:" in captured.err


def test_runner_cli_directory_input(tmp_path: Path, capsys):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    s1 = scenarios_dir / "s1.json"
    s1.write_text(json.dumps({"name": "s1", "role": "pm", "prompt": "p", "judge": "j"}))
    s2 = scenarios_dir / "s2.json"
    s2.write_text(json.dumps({"name": "s2", "role": "cpo", "prompt": "p2", "checks": {"includes": ["ok"]}}))

    exit_code = run_checker_cli([str(scenarios_dir)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Passed static validation" in captured.out
    assert "PASSED:" in captured.out


def test_runner_cli_directory_with_failures(tmp_path: Path, capsys):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    s1 = scenarios_dir / "s1.json"
    s1.write_text(json.dumps({"name": "s1", "role": "pm", "prompt": "p", "judge": "j"}))
    s2 = scenarios_dir / "broken.json"
    s2.write_text('{"name": "broken", ')

    exit_code = run_checker_cli([str(scenarios_dir)])
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "Failed static validation" in captured.err


def test_runner_cli_empty_directory(tmp_path: Path, capsys):
    scenarios_dir = tmp_path / "empty_scenarios"
    scenarios_dir.mkdir()

    exit_code = run_checker_cli([str(scenarios_dir)])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "No scenario files found" in captured.err


def test_validate_scenario_paths_with_directory(tmp_path: Path):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    s1 = scenarios_dir / "s1.json"
    s1.write_text(json.dumps({"name": "s1", "role": "pm", "prompt": "p", "judge": "j"}))

    all_valid, results = validate_scenario_paths([scenarios_dir])
    assert all_valid is True
    assert str(s1) in results
    assert results[str(s1)] == []

