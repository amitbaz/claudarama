"""Static validator and schema checker for Claudarama scenario files."""

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Optional

from claudarama.db import CAST

ALLOWED_TOP_LEVEL_KEYS = {"name", "description", "role", "prompt", "checks", "judge", "steps"}
ALLOWED_CHECKS_KEYS = {"includes", "excludes"}
ALLOWED_TURN_KEYS = {"role", "ticket", "calls"}


@dataclass
class ScenarioStep:
    type: str

@dataclass
class MockLlmTurnsStep(ScenarioStep):
    """Scripted turns the office runs side by side; the step ends when each has ended."""
    type: str = "mock_llm_turns"
    turns: list[dict[str, Any]] = field(default_factory=list)

@dataclass
class CeoActionStep(ScenarioStep):
    """The CEO's answer at the gate that is waiting (``input``, with the ``reason`` for a NO), what
    the CEO's Session asks of the office (``calls``), or the ``claudarama`` command the CEO runs
    (``command``: only ``status``)."""
    type: str = "ceo_action"
    input: str = ""
    reason: str = ""
    calls: list[dict[str, Any]] = field(default_factory=list)
    command: str = ""

@dataclass
class ScenarioChecks:
    """Assertions to evaluate on agent output."""
    includes: list[str] = field(default_factory=list)
    excludes: list[str] = field(default_factory=list)


@dataclass
class Scenario:
    """Represents a validated scenario definition."""
    name: str
    role: str
    prompt: str
    description: str = ""
    checks: ScenarioChecks = field(default_factory=ScenarioChecks)
    judge: Optional[str] = None
    steps: list[ScenarioStep] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Outcome of validating a scenario object or file."""
    valid: bool
    errors: list[str] = field(default_factory=list)
    scenario: Optional[Scenario] = None


class ScenarioValidationError(ValueError):
    """Raised when a scenario definition or file fails schema validation."""
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _validate_string_list(
    raw_list: Any,
    field_name: str,
    errors: list[str],
) -> list[str]:
    """Validate that raw_list is a list of non-empty, non-whitespace strings."""
    if not isinstance(raw_list, list):
        errors.append(f"'{field_name}' must be a list of non-empty strings.")
        return []

    validated_strings: list[str] = []
    has_invalid_element = False

    for item in raw_list:
        if not isinstance(item, str) or not item.strip():
            has_invalid_element = True
        else:
            validated_strings.append(item.strip())

    if has_invalid_element or len(raw_list) == 0:
        errors.append(f"'{field_name}' must be a list of non-empty strings.")
        return []

    return validated_strings


def _validate_regex_patterns(
    patterns: list[str],
    field_name: str,
    errors: list[str],
) -> None:
    """Validate that all patterns compile as valid regular expressions."""
    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            errors.append(f"Invalid regex in '{field_name}' ({pattern!r}): {exc}")


def _validate_calls(calls: Any, where: str, errors: list[str], may_run: bool) -> None:
    """Each scripted call names one of the office's tools (``tool``, ``args``) or, in a turn, a command (``run``)."""
    if not isinstance(calls, list) or not calls:
        errors.append(f"{where} must have a non-empty 'calls' list.")
        return
    for call in calls:
        is_tool = isinstance(call, dict) and isinstance(call.get("tool"), str) and isinstance(call.get("args", {}), dict)
        is_run = (
            may_run and isinstance(call, dict) and isinstance(call.get("run"), list)
            and bool(call["run"]) and all(isinstance(arg, str) for arg in call["run"])
        )
        if is_tool == is_run:  # neither, or both at once
            shapes = "{'tool', 'args'} or {'run'}" if may_run else "{'tool', 'args'}"
            errors.append(f"{where} has a call that is not {shapes}: {call!r}")


def _validate_turn(turn: Any, scenario_role: Any, where: str, errors: list[str]) -> None:
    """A scripted turn: the Role that runs it (the scenario's when it names none), its ticket and its calls."""
    if not isinstance(turn, dict):
        errors.append(f"{where} has a turn that is not an object.")
        return
    unexpected = sorted(set(turn) - ALLOWED_TURN_KEYS)
    if unexpected:
        errors.append(f"{where} has a turn with unrecognized fields: {', '.join(unexpected)}")
    role = turn.get("role", scenario_role)
    if not isinstance(role, str) or role not in CAST:
        errors.append(f"{where} has a turn for {role!r}, which is not a Role of the cast.")
    if not isinstance(turn.get("ticket", ""), str):
        errors.append(f"{where} has a turn whose 'ticket' is not a string.")
    _validate_calls(turn.get("calls"), f"{where}, the turn for {role!r},", errors, may_run=True)


def validate_scenario(data: Any) -> ValidationResult:
    """Validate raw scenario data against the schema without making LLM calls."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return ValidationResult(valid=False, errors=["Scenario definition must be a JSON object (dict)."])

    # Disallow unexpected top-level keys (e.g. typos like 'roel')
    unexpected_keys = sorted(set(data.keys()) - ALLOWED_TOP_LEVEL_KEYS)
    if unexpected_keys:
        errors.append(f"Unrecognized fields in scenario: {', '.join(unexpected_keys)}")

    # Required fields: name, role, prompt
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("Field 'name' is required and must be a non-empty string.")

    role = data.get("role")
    if not isinstance(role, str) or not role.strip():
        errors.append("Field 'role' is required and must be a non-empty string.")

    prompt = data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        errors.append("Field 'prompt' is required and must be a non-empty string.")

    # Optional description
    description = data.get("description", "")
    if description is not None and not isinstance(description, str):
        errors.append("Field 'description' must be a string if provided.")
    elif description is None:
        description = ""

    # Optional judge
    judge = data.get("judge")
    if judge is not None:
        if not isinstance(judge, str) or not judge.strip():
            errors.append("Field 'judge' must be a non-empty string if provided.")

    # Parse and validate checks
    includes: list[str] = []
    excludes: list[str] = []
    checks_declared = False

    checks_raw = data.get("checks")
    if checks_raw is not None:
        checks_declared = True
        if not isinstance(checks_raw, dict):
            errors.append("Field 'checks' must be an object containing 'includes' and/or 'excludes'.")
        else:
            unexpected_checks_keys = sorted(set(checks_raw.keys()) - ALLOWED_CHECKS_KEYS)
            if unexpected_checks_keys:
                errors.append(f"Unrecognized fields in 'checks': {', '.join(unexpected_checks_keys)}")

            if "includes" in checks_raw:
                includes = _validate_string_list(checks_raw["includes"], "checks.includes", errors)
                _validate_regex_patterns(includes, "checks.includes", errors)

            if "excludes" in checks_raw:
                excludes = _validate_string_list(checks_raw["excludes"], "checks.excludes", errors)
                _validate_regex_patterns(excludes, "checks.excludes", errors)

    # Require at least one validation criterion, but only flag if no other checks/judge errors occurred
    has_active_assertions = bool(includes or excludes or (isinstance(judge, str) and judge.strip()))
    if not has_active_assertions and not checks_declared and judge is None:
        errors.append("Scenario must declare at least one check ('checks.includes', 'checks.excludes', or 'judge').")


    parsed_steps = []
    steps_raw = data.get("steps", [])
    if not isinstance(steps_raw, list):
        errors.append("Field 'steps' must be a list if provided.")
    else:
        for i, step in enumerate(steps_raw):
            if not isinstance(step, dict):
                errors.append(f"Step at index {i} must be an object.")
                continue
            step_type = step.get("type")
            if step_type not in ("mock_llm_turns", "ceo_action"):
                errors.append(f"Step at index {i} has invalid type: {step_type}")
            elif step_type == "mock_llm_turns":
                if "turns" not in step or not isinstance(step["turns"], list):
                    errors.append(f"Step at index {i} (mock_llm_turns) must have a 'turns' list.")
                else:
                    for turn in step["turns"]:
                        _validate_turn(turn, role, f"Step at index {i} (mock_llm_turns)", errors)
                    parsed_steps.append(MockLlmTurnsStep(turns=step["turns"]))
            elif step_type == "ceo_action":
                if "command" in step:
                    if step != {"type": "ceo_action", "command": "status"}:
                        errors.append(f"Step at index {i} (ceo_action) may run only the 'command' status, with nothing beside it.")
                    parsed_steps.append(CeoActionStep(command="status"))
                elif "calls" in step and "input" not in step:
                    _validate_calls(step["calls"], f"Step at index {i} (ceo_action)", errors, may_run=False)
                    parsed_steps.append(CeoActionStep(calls=step["calls"]))
                elif "calls" in step or step.get("input") not in ("YES", "NO", "DISCUSS"):
                    errors.append(
                        f"Step at index {i} (ceo_action) must have either an 'input' string of YES, NO, or DISCUSS, "
                        "or a 'calls' list."
                    )
                else:
                    reason = step.get("reason", "")
                    if not isinstance(reason, str) or "\n" in reason or bool(reason.strip()) != (step["input"] == "NO"):
                        errors.append(f"Step at index {i} (ceo_action) must give a one-line 'reason' with NO, and only with NO.")
                    parsed_steps.append(CeoActionStep(input=step["input"], reason=reason))

    if errors:
        return ValidationResult(valid=False, errors=errors)

    assert isinstance(name, str)
    assert isinstance(role, str)
    assert isinstance(prompt, str)

    scenario = Scenario(
        name=name.strip(),
        role=role.strip(),
        prompt=prompt.strip(),
        description=description.strip(),
        checks=ScenarioChecks(includes=includes, excludes=excludes),
        judge=judge.strip() if judge else None,
        steps=parsed_steps,
    )
    return ValidationResult(valid=True, errors=[], scenario=scenario)


def validate_scenario_file(file_path: str | Path) -> ValidationResult:
    """Read a scenario JSON file and validate its schema."""
    path = Path(file_path)
    if not path.is_file():
        return ValidationResult(valid=False, errors=[f"Scenario file not found: {path}"])

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as exc:
        return ValidationResult(valid=False, errors=[f"Failed to read scenario file {path}: {exc}"])

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        return ValidationResult(valid=False, errors=[f"Malformed JSON in {path}: {exc}"])

    return validate_scenario(data)


def load_scenario(file_path: str | Path) -> Scenario:
    """Load and validate a scenario from file, raising ScenarioValidationError on error."""
    result = validate_scenario_file(file_path)
    if not result.valid or result.scenario is None:
        raise ScenarioValidationError(result.errors)
    return result.scenario


def validate_scenario_paths(paths: list[str | Path]) -> tuple[bool, dict[str, list[str]]]:
    """Validate multiple scenario files or directories containing scenario files.

    Returns:
        (all_valid, results_dict) where results_dict maps file path string to list of error strings.
    """
    all_valid = True
    results: dict[str, list[str]] = {}

    for path in paths:
        p = Path(path)
        if p.is_dir():
            json_files = sorted(p.glob("**/*.json"))
            if not json_files:
                results[str(path)] = [f"No scenario files found in directory: {path}"]
                all_valid = False
            for jf in json_files:
                path_str = str(jf)
                res = validate_scenario_file(jf)
                results[path_str] = res.errors
                if not res.valid:
                    all_valid = False
        else:
            path_str = str(path)
            res = validate_scenario_file(p)
            results[path_str] = res.errors
            if not res.valid:
                all_valid = False

    return all_valid, results

