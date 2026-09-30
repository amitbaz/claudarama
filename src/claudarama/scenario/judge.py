"""Strict JSON judge and excludes self-test logic for Claudarama scenario evaluation."""

from dataclasses import dataclass
import json
import re
from typing import Any, Optional

ALLOWED_JUDGE_KEYS = {"pass", "reason"}
DEFAULT_DUMMY_TEMPLATE = "Task execution completed successfully.\n{injected}\nOperation finished cleanly."


@dataclass
class JudgeResult:
    """Evaluation result produced by parsing judge LLM output."""
    passed: bool
    reason: str
    raw_output: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert result to standard {"pass": bool, "reason": str} dict."""
        return {"pass": self.passed, "reason": self.reason}


@dataclass
class CheckResult:
    """Outcome of checking an individual pattern against text."""
    passed: bool
    pattern: str
    matched: bool
    message: str = ""


@dataclass
class ExcludesSelfTestResult:
    """Outcome of self-testing an excludes constraint against planted text."""
    passed: bool
    pattern: str
    dummy_reply: str
    injected_text: str
    message: str = ""


def _strip_markdown_fences(text: str) -> str:
    """Remove surrounding markdown code blocks (e.g. ```json ... ```) if present."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def _match_pattern(pattern: str, text: str) -> tuple[Optional[re.Match], Optional[str]]:
    """Execute a regex search on text, returning (match, error_message)."""
    try:
        return re.search(pattern, text), None
    except re.error as exc:
        return None, str(exc)


def parse_judge_output(raw_output: str) -> JudgeResult:
    """Strictly parse LLM judge output and ensure it matches the {"pass": bool, "reason": str} shape.
    
    Any malformed JSON, schema violation, or missing field fails the evaluation.
    """
    if not isinstance(raw_output, str) or not raw_output.strip():
        return JudgeResult(
            passed=False,
            reason="Empty or non-string judge output.",
            raw_output=str(raw_output) if raw_output is not None else "",
        )

    clean_text = _strip_markdown_fences(raw_output)

    try:
        data = json.loads(clean_text)
    except json.JSONDecodeError as exc:
        return JudgeResult(
            passed=False,
            reason=f"Malformed JSON in judge output: {exc}",
            raw_output=raw_output,
        )

    if not isinstance(data, dict):
        return JudgeResult(
            passed=False,
            reason="Judge output must be a JSON object (dict).",
            raw_output=raw_output,
        )

    extra_keys = sorted(set(data.keys()) - ALLOWED_JUDGE_KEYS)
    if extra_keys:
        return JudgeResult(
            passed=False,
            reason=f"Unrecognized fields in judge output: {', '.join(extra_keys)}",
            raw_output=raw_output,
        )

    if "pass" not in data:
        return JudgeResult(
            passed=False,
            reason="Missing required field 'pass' in judge output.",
            raw_output=raw_output,
        )

    if type(data["pass"]) is not bool:
        return JudgeResult(
            passed=False,
            reason=f"Field 'pass' must be a boolean, got {type(data['pass']).__name__}.",
            raw_output=raw_output,
        )

    if "reason" not in data:
        return JudgeResult(
            passed=False,
            reason="Missing required field 'reason' in judge output.",
            raw_output=raw_output,
        )

    if not isinstance(data["reason"], str):
        return JudgeResult(
            passed=False,
            reason=f"Field 'reason' must be a string, got {type(data['reason']).__name__}.",
            raw_output=raw_output,
        )

    return JudgeResult(
        passed=data["pass"],
        reason=data["reason"].strip(),
        raw_output=raw_output,
    )


# Alias for parse_judge_output to match specification naming
strict_json_judge = parse_judge_output


def evaluate_exclude_pattern(reply: str, pattern: str) -> CheckResult:
    """Evaluate an exclude pattern against an agent reply.
    
    Returns:
        CheckResult with passed=True if pattern is NOT found in reply.
        CheckResult with passed=False if pattern IS found (constraint violated).
    """
    match, err = _match_pattern(pattern, reply)
    if err is not None:
        return CheckResult(
            passed=False,
            pattern=pattern,
            matched=False,
            message=f"Invalid regular expression in exclude pattern: {err}",
        )

    if match is not None:
        return CheckResult(
            passed=False,
            pattern=pattern,
            matched=True,
            message=f"Excluded pattern {pattern!r} matched forbidden content: {match.group(0)!r}",
        )

    return CheckResult(
        passed=True,
        pattern=pattern,
        matched=False,
        message=f"Excluded pattern {pattern!r} not found in reply.",
    )


def evaluate_excludes(reply: str, patterns: list[str]) -> list[CheckResult]:
    """Evaluate multiple exclude patterns against an agent reply."""
    return [evaluate_exclude_pattern(reply, p) for p in patterns]


def evaluate_include_pattern(reply: str, pattern: str) -> CheckResult:
    """Evaluate an include pattern against an agent reply.
    
    Returns:
        CheckResult with passed=True if pattern IS found in reply.
        CheckResult with passed=False if pattern is NOT found.
    """
    match, err = _match_pattern(pattern, reply)
    if err is not None:
        return CheckResult(
            passed=False,
            pattern=pattern,
            matched=False,
            message=f"Invalid regular expression in include pattern: {err}",
        )

    if match is not None:
        return CheckResult(
            passed=True,
            pattern=pattern,
            matched=True,
            message=f"Required pattern {pattern!r} matched content: {match.group(0)!r}",
        )

    return CheckResult(
        passed=False,
        pattern=pattern,
        matched=False,
        message=f"Required pattern {pattern!r} was not found in reply.",
    )


def evaluate_includes(reply: str, patterns: list[str]) -> list[CheckResult]:
    """Evaluate multiple include patterns against an agent reply."""
    return [evaluate_include_pattern(reply, p) for p in patterns]


def _derive_injection_token(pattern: str) -> str:
    """Derive a representative trigger token from a pattern for self-testing."""
    token = pattern.replace(r"\b", "").replace("^", "").replace("$", "").replace(r"\A", "").replace(r"\Z", "")
    token = re.sub(r"\\s[+*]?", " ", token)
    token = re.sub(r"\\d[+*]?", "123", token)
    token = re.sub(r"\\w[+*]?", "token", token)
    token = re.sub(r"\[0-9\][+*]?", "123", token)
    token = re.sub(r"\[a-z\][+*]?", "abc", token)
    token = re.sub(r"\[a-zA-Z\][+*]?", "abc", token)
    token = re.sub(r"\\([./\-])", r"\1", token)
    if "(" in token and "|" in token:
        token = re.sub(r"\(|\)", "", token)
        token = token.split("|")[0]
    token = token.strip()
    return token if token else pattern


def self_test_excludes(
    pattern: str,
    injection_text: Optional[str] = None,
    dummy_reply: Optional[str] = None,
) -> ExcludesSelfTestResult:
    """Self-test an excludes constraint by injecting it into a dummy reply.
    
    Verifies that the pattern successfully detects the injected text and triggers a failure.
    If the pattern does not match the planted reply, the self-test fails.
    """
    injected = injection_text if injection_text is not None else _derive_injection_token(pattern)

    if dummy_reply is not None:
        if "{injected}" in dummy_reply:
            planted_reply = dummy_reply.format(injected=injected)
        else:
            planted_reply = f"{dummy_reply}\n{injected}"
    else:
        planted_reply = DEFAULT_DUMMY_TEMPLATE.format(injected=injected)

    check_res = evaluate_exclude_pattern(planted_reply, pattern)

    if check_res.matched:
        return ExcludesSelfTestResult(
            passed=True,
            pattern=pattern,
            dummy_reply=planted_reply,
            injected_text=injected,
            message=f"Excluded pattern {pattern!r} successfully triggered failure on planted reply.",
        )

    return ExcludesSelfTestResult(
        passed=False,
        pattern=pattern,
        dummy_reply=planted_reply,
        injected_text=injected,
        message=f"Excluded pattern {pattern!r} failed to trigger failure on planted reply: {check_res.message}",
    )


# Alias for self_test_excludes
verify_excludes_pattern = self_test_excludes


def self_test_all_excludes(patterns: list[str]) -> list[ExcludesSelfTestResult]:
    """Run self-test on every excludes pattern in a list."""
    return [self_test_excludes(p) for p in patterns]
