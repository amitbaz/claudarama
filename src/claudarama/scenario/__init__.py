"""Scenario harness package for Claudarama."""

from claudarama.scenario.cli import run_checker_cli
from claudarama.scenario.judge import (
    CheckResult,
    ExcludesSelfTestResult,
    JudgeResult,
    evaluate_exclude_pattern,
    evaluate_excludes,
    evaluate_include_pattern,
    evaluate_includes,
    parse_judge_output,
    self_test_all_excludes,
    self_test_excludes,
    strict_json_judge,
    verify_excludes_pattern,
)
from claudarama.scenario.validator import (
    Scenario,
    ScenarioChecks,
    ScenarioValidationError,
    ValidationResult,
    load_scenario,
    validate_scenario,
    validate_scenario_file,
    validate_scenario_paths,
)

__all__ = [
    "CheckResult",
    "ExcludesSelfTestResult",
    "JudgeResult",
    "Scenario",
    "ScenarioChecks",
    "ScenarioValidationError",
    "ValidationResult",
    "evaluate_exclude_pattern",
    "evaluate_excludes",
    "evaluate_include_pattern",
    "evaluate_includes",
    "load_scenario",
    "parse_judge_output",
    "run_checker_cli",
    "self_test_all_excludes",
    "self_test_excludes",
    "strict_json_judge",
    "validate_scenario",
    "validate_scenario_file",
    "validate_scenario_paths",
    "verify_excludes_pattern",
]
