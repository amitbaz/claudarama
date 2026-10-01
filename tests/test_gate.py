"""Gate seams: allowlist generation, the gate hook (hook JSON on stdin) and the supervisor's settings."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from claudarama.db import get_turn, init_db, queue_turn
from claudarama.gate import CORE_DENY, OFFICE_ENV, build_allowlist, write_turn_settings
from claudarama.supervisor import Supervisor


def _pack(tmp_path: Path, stack: str = "", gates: str = "") -> Path:
    pack = tmp_path / ".claudarama"
    pack.mkdir(exist_ok=True)
    (pack / "stack.yaml").write_text(stack)
    (pack / "gates.yaml").write_text(gates)
    return pack


STACK = 'commands:\n  test: "pytest -q"\n  local_ci: "make ci"\n'
GATES = 'deny_rules:\n  - "Bash(git push --force *)"\n'


def _hook(tmp_path: Path, payload: dict | str, env_file: bool = True) -> dict:
    """Run the generated hook command as Claude Code does, in a bare environment, and return the decision."""
    command, settings = _generated(tmp_path)
    out = _run_hook_command(tmp_path, command, settings, payload, env_file)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)["hookSpecificOutput"]


def _bash(tmp_path, command):
    return _hook(tmp_path, {"tool_name": "Bash", "tool_input": {"command": command}})


def test_allowlist_merges_core_stack_and_gates(tmp_path):
    allow, deny = build_allowlist(_pack(tmp_path, STACK, GATES))
    assert "Bash(git status *)" in allow
    assert "Bash(pytest -q)" in allow and "Bash(pytest -q *)" in allow
    assert "Bash(make ci)" in allow
    assert deny[-1] == "Bash(git push --force *)" and "Bash(git config *)" in deny


def test_allowlist_survives_missing_pack_files(tmp_path):
    allow, deny = build_allowlist(tmp_path / "nope")
    assert "Bash(git status *)" in allow and deny == CORE_DENY


def test_hook_blocks_without_office_env(tmp_path):
    decision = _hook(tmp_path, {"tool_name": "Read", "tool_input": {}}, env_file=False)
    assert decision["permissionDecision"] == "deny" and OFFICE_ENV in decision["permissionDecisionReason"]


@pytest.mark.parametrize("command", [
    "git status",
    "git status && pytest -q",
    "git status || make ci",
    "git status; git log",
    "git log | grep fix",
    "echo $(git rev-parse HEAD)",
    "echo `git rev-parse HEAD`",
    "git commit -m 'a && rm -rf /'",  # chaining chars inside quotes are data
    'git log 2>&1',
])
def test_hook_allows_fully_allowed_commands(tmp_path, command):
    assert _bash(tmp_path, command)["permissionDecision"] == "allow"


@pytest.mark.parametrize("command,rule", [
    ("git status && rm -rf x", "rm -rf x"),
    ("git status || rm x", "rm x"),
    ("git status; rm x", "rm x"),
    ("git status | tee out", "tee out"),
    ("echo $(rm x)", "rm x"),
    ("echo `rm x`", "rm x"),
    ('echo "$(rm x)"', "rm x"),
    ("git push --force origin main", "Bash(git push --force*)"),
    ("git status && git push --force origin main", "Bash(git push --force*)"),
    ("git -c alias.x=!sh x", "Bash(git -c *)"),
    ("git config alias.x '!sh'", "Bash(git config *)"),
    ("echo hi > /etc/passwd", "file redirection"),
])
def test_hook_denies_any_disallowed_part_and_names_the_rule(tmp_path, command, rule):
    decision = _bash(tmp_path, command)
    assert decision["permissionDecision"] == "deny"
    assert rule in decision["permissionDecisionReason"]


@pytest.mark.parametrize("command", ["git status && (rm x)", "echo $(git log", "echo 'oops", "echo `git log"])
def test_hook_denies_unparseable_commands(tmp_path, command):
    decision = _bash(tmp_path, command)
    assert decision["permissionDecision"] == "deny"
    assert "parse" in decision["permissionDecisionReason"]


@pytest.mark.parametrize("payload", ["not json", "[]", '{"tool_name": "Bash"}'])
def test_hook_denies_garbage_input(tmp_path, payload):
    assert _hook(tmp_path, payload)["permissionDecision"] == "deny"


def test_hook_fails_closed_when_settings_unreadable(tmp_path):
    command, _ = _generated(tmp_path)
    r = subprocess.run(["sh", "-c", command], input='{"tool_name": "Read", "tool_input": {}}', capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", OFFICE_ENV: str(tmp_path / "missing.json")})
    assert json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize("payload", [
    {"tool_name": "Read", "tool_input": {"file_path": "~/.claudarama/office.db"}},
    {"tool_name": "Read", "tool_input": {"file_path": str(Path.home() / ".claudarama" / "x" / "office.db")}},
    {"tool_name": "Edit", "tool_input": {"file_path": str(Path.home() / ".claudarama" / "office.db")}},
    {"tool_name": "Bash", "tool_input": {"command": "cat ~/.claudarama/x/office.db"}},
    {"tool_name": "Bash", "tool_input": {"command": "cat $HOME/.claudarama/x"}},
    {"tool_name": "Bash", "tool_input": {"command": f"cat {Path.home()}/.claudarama/x"}},
    {"tool_name": "Grep", "tool_input": {"pattern": "t", "path": "~/.claudarama"}},
    {"tool_name": "Bash", "tool_input": {"command": "cat ~/.claud\'\'arama/x"}},
    {"tool_name": "Bash", "tool_input": {"command": "cat ~/.c*/x"}},
    {"tool_name": "Bash", "tool_input": {"command": 'cat "$HOME"/.claudarama/x'}},
    {"tool_name": "Bash", "tool_input": {"command": "cat ~/.CLAUDARAMA/x"}},
    {"tool_name": "Read", "cwd": str(Path.home() / "x"), "tool_input": {"file_path": "../.claudarama/office.db"}},
])
def test_hook_denies_access_to_office_state_dir(tmp_path, payload):
    decision = _hook(tmp_path, payload)
    assert decision["permissionDecision"] == "deny"
    assert "~/.claudarama" in decision["permissionDecisionReason"]


def test_hook_allows_the_projects_own_pack_dir(tmp_path):
    payload = {"tool_name": "Read", "tool_input": {"file_path": ".claudarama/company.md"}}
    assert _hook(tmp_path, payload)["permissionDecision"] == "allow"


def test_hook_matches_non_bash_tools_against_allowlist(tmp_path):
    assert _hook(tmp_path, {"tool_name": "mcp__claudarama__send", "tool_input": {}})["permissionDecision"] == "allow"
    decision = _hook(tmp_path, {"tool_name": "WebFetch", "tool_input": {"url": "http://x"}})
    assert decision["permissionDecision"] == "deny" and "WebFetch" in decision["permissionDecisionReason"]


# ---------------------------------------------------------------------------
# Supervisor seam
# ---------------------------------------------------------------------------


def test_every_turn_launches_with_generated_settings_and_dontask(tmp_path):
    db = tmp_path / "office.db"
    init_db(db)
    import sqlite3
    turn_id = queue_turn(db, "fullstack-engineer", kind="ritual")
    pack = _pack(tmp_path, STACK, GATES)
    sup = Supervisor(db, pack, tmp_path)

    launch = sup.build_launch(get_turn(db, turn_id))

    cmd = launch.cmd
    assert cmd[cmd.index("--permission-mode") + 1] == "dontAsk"
    settings_path = Path(cmd[cmd.index("--settings") + 1])
    settings = json.loads(settings_path.read_text())
    allow, deny = build_allowlist(pack)
    assert settings["permissions"] == {"allow": allow, "deny": deny}
    hook = settings["hooks"]["PreToolUse"][0]["hooks"][0]
    assert "--allowedTools" not in cmd
    assert launch.env["CLAUDARAMA_OFFICE"] == str(settings_path)


# ---------------------------------------------------------------------------
# The hook as Claude Code runs it: the generated command line, in a bare environment
# ---------------------------------------------------------------------------


def _run_hook_command(tmp_path: Path, command: str, settings: dict, payload: dict | str, env_file: bool = True):
    settings_file = tmp_path / "t1.settings.json"
    settings_file.write_text(json.dumps(settings))
    env = {"PATH": "/usr/bin:/bin", "HOME": str(Path.home())}  # no PYTHONPATH: nothing but the install
    if env_file:
        env[OFFICE_ENV] = str(settings_file)
    return subprocess.run(
        ["sh", "-c", command], input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True, text=True, env=env,
    )


def _generated(tmp_path: Path) -> tuple[str, dict]:
    path = tmp_path / "gen.settings.json"
    write_turn_settings(_pack(tmp_path, STACK, GATES), path)
    settings = json.loads(path.read_text())
    return settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"], settings


def test_generated_hook_runs_without_the_checkout_on_the_path(tmp_path):
    command, settings = _generated(tmp_path)
    bash = lambda c: {"tool_name": "Bash", "tool_input": {"command": c}}
    ok = _run_hook_command(tmp_path, command, settings, bash("git status"))
    assert json.loads(ok.stdout)["hookSpecificOutput"]["permissionDecision"] == "allow"
    bad = _run_hook_command(tmp_path, command, settings, bash("curl http://x"))
    out = json.loads(bad.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "curl" in out["permissionDecisionReason"]


def test_internal_error_blocks_with_a_reason_the_model_sees(tmp_path):
    command, _ = _generated(tmp_path)
    r = _run_hook_command(tmp_path, command, {"permissions": {}}, {"tool_name": "Bash", "tool_input": {"command": "git status"}})
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "gate hook error" in out["permissionDecisionReason"]


def test_hook_that_cannot_start_exits_2_so_claude_code_blocks(tmp_path):
    command, settings = _generated(tmp_path)
    broken = command.replace("gate.py", "no_such_gate.py")
    assert broken != command
    r = _run_hook_command(tmp_path, broken, settings, {"tool_name": "Read", "tool_input": {}})
    assert r.returncode == 2 and "gate hook failed" in r.stderr
