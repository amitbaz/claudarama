"""One allowlist, two walls: the turn's native ``permissions`` and the PreToolUse gate hook.

``build_allowlist`` makes the list from the core rules, the pack's ``gates.yaml`` and the
commands in ``stack.yaml``. The supervisor writes it into each turn's ``--settings``. The
hook (``python -m claudarama.gate``) reads that same file, named by ``CLAUDARAMA_OFFICE``,
and is silent when the variable is unset. Gated actions are never on this list (ADR-0002).
"""
import json
import os
import re
import sys
from pathlib import Path

OFFICE_ENV = "CLAUDARAMA_OFFICE"

CORE_ALLOW = [
    "Read", "Glob", "Grep", "Edit", "Write", "mcp__claudarama__*",
    "Bash(git *)", "Bash(gh issue *)", "Bash(gh pr create *)", "Bash(gh pr view *)",
    "Bash(gh pr list *)", "Bash(gh pr diff *)", "Bash(gh pr checks *)", "Bash(gh pr comment *)",
    "Bash(ls *)", "Bash(cat *)", "Bash(head *)", "Bash(tail *)", "Bash(wc *)",
    "Bash(grep *)", "Bash(rg *)", "Bash(echo *)", "Bash(pwd)",
]


def _block(text: str, key: str) -> list[str]:
    """Lines indented under a top-level ``key:`` (flat yaml only, like ``load_org_settings``)."""
    lines, found = [], False
    for line in text.splitlines():
        if not found:
            found = line.rstrip() == f"{key}:"
        elif line[:1] in (" ", "\t"):
            lines.append(line.strip())
        elif line.strip() and not line.startswith("#"):
            break
    return lines


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def build_allowlist(pack_dir: Path) -> tuple[list[str], list[str]]:
    """Return ``(allow, deny)`` rules from the core list, ``stack.yaml`` commands and ``gates.yaml`` deny rules."""
    allow = list(CORE_ALLOW)
    for line in _block(_read(pack_dir / "stack.yaml"), "commands"):
        cmd = line.partition(":")[2].strip().strip("\"'")
        if cmd:
            allow += [f"Bash({cmd})", f"Bash({cmd} *)"]
    deny = [
        line[1:].strip().strip("\"'")
        for line in _block(_read(pack_dir / "gates.yaml"), "deny_rules")
        if line.startswith("-")
    ]
    return allow, deny


# --- matching ---------------------------------------------------------------


def _glob(pattern: str, text: str) -> bool:
    """``*`` matches anything. A trailing `` *`` also matches the bare command."""
    pattern = pattern.replace(":*", " *")  # legacy prefix syntax
    if pattern.endswith(" *") and text == pattern[:-2]:
        return True
    return re.fullmatch(".*".join(map(re.escape, pattern.split("*"))), text, re.DOTALL) is not None


def _rule_matches(rule: str, tool: str, part: str | None) -> bool:
    name, paren, arg = rule.partition("(")
    if not paren:
        return _glob(name, tool)
    return tool == "Bash" and name == "Bash" and part is not None and _glob(arg.removesuffix(")"), part)


# --- shell splitting --------------------------------------------------------


class ParseError(Exception):
    pass


def _parse(s: str, i: int, in_sub: bool) -> tuple[list[str], int]:
    """Split ``s`` into simple commands; ``$(...)`` and backticks yield their own commands."""
    parts: list[str] = []
    cur: list[str] = []

    def flush() -> None:
        text = "".join(cur).strip()
        if text:
            parts.append(text)
        cur.clear()

    def backtick(i: int) -> int:
        j = s.find("`", i + 1)
        if j < 0:
            raise ParseError("unclosed backtick")
        parts.extend(_parse(s[i + 1:j], 0, False)[0])
        return j + 1

    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            cur.append(s[i:i + 2])
            i += 2
        elif c == "'":
            j = s.find("'", i + 1)
            if j < 0:
                raise ParseError("unclosed single quote")
            cur.append(s[i:j + 1])
            i = j + 1
        elif c == '"':
            cur.append(c)
            i += 1
            while True:
                if i >= n:
                    raise ParseError("unclosed double quote")
                if s[i] == "\\":
                    cur.append(s[i:i + 2])
                    i += 2
                elif s[i] == '"':
                    cur.append('"')
                    i += 1
                    break
                elif s.startswith("$(", i):
                    sub, i = _parse(s, i + 2, True)
                    parts.extend(sub)
                elif s[i] == "`":
                    i = backtick(i)
                else:
                    cur.append(s[i])
                    i += 1
        elif s.startswith("$(", i):
            sub, i = _parse(s, i + 2, True)
            parts.extend(sub)
        elif c == "`":
            i = backtick(i)
        elif c == ")":
            if not in_sub:
                raise ParseError("unbalanced )")
            flush()
            return parts, i + 1
        elif c == "(":
            raise ParseError("subshell or grouping")
        elif c in ";\n":
            flush()
            i += 1
        elif c == "|":
            flush()
            i += 2 if s[i + 1:i + 2] in ("|", "&") else 1
        elif c == "&" and s[i + 1:i + 2] == "&":
            flush()
            i += 2
        elif c == "&" and s[i - 1:i] not in ("<", ">") and s[i + 1:i + 2] != ">":
            flush()  # background
            i += 1
        else:
            cur.append(c)
            i += 1
    if in_sub:
        raise ParseError("unclosed $(")
    flush()
    return parts, i


# --- decision ---------------------------------------------------------------

PATH_KEYS = ("file_path", "path", "notebook_path")


def _state_dir_access(tool_input: dict) -> bool:
    home = str(Path.home())
    state = os.path.join(home, ".claudarama")
    for key in PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str):
            full = os.path.abspath(os.path.expanduser(value))
            if full == state or full.startswith(state + os.sep):
                return True
    command = tool_input.get("command")
    if isinstance(command, str):
        return re.search(rf"(?:~|\$HOME|\$\{{HOME\}}|{re.escape(home)})/\.claudarama(?![\w.-])", command) is not None
    return False


def decide(payload: object, allow: list[str], deny: list[str]) -> tuple[bool, str]:
    """Return ``(allowed, reason)`` for one PreToolUse payload."""
    if not isinstance(payload, dict) or not isinstance(payload.get("tool_name"), str):
        return False, "cannot parse hook input"
    tool, tool_input = payload["tool_name"], payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return False, "cannot parse hook input: no tool_input"
    if _state_dir_access(tool_input):
        return False, "access to ~/.claudarama/ is denied (office state and owner token)"
    parts: list[str | None] = [None]
    if tool == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str):
            return False, "cannot parse hook input: no command"
        try:
            parts = _parse(command, 0, False)[0]
        except ParseError as e:
            return False, f"cannot parse command ({e}); denied because the gate fails closed"
        if not parts:
            return False, "cannot parse command: nothing to run"
    for part in parts:
        for rule in deny:
            if _rule_matches(rule, tool, part):
                return False, f"denied by rule {rule}"
        if not any(_rule_matches(rule, tool, part) for rule in allow):
            return False, f"{part or tool} is not on the allowlist (no allow rule matches)"
    return True, "on the allowlist"


def main() -> None:
    try:
        settings_path = os.environ.get(OFFICE_ENV)
        if not settings_path:
            return  # not an office turn: stay out of the way
        perms = json.loads(Path(settings_path).read_text(encoding="utf-8"))["permissions"]
        try:
            payload = json.load(sys.stdin)
        except ValueError:
            payload = None
        allowed, reason = decide(payload, perms["allow"], perms["deny"])
    except Exception as e:  # fail closed
        allowed, reason = False, f"gate hook error: {e}"
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow" if allowed else "deny",
        "permissionDecisionReason": reason,
    }}))


if __name__ == "__main__":
    main()
