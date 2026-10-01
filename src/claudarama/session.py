import json
import subprocess
import sys
from pathlib import Path

from claudarama.brief import build_brief
from claudarama.db import (
    diagnosis_gates,
    end_session,
    epic_gates,
    get_office_db_path,
    get_owner_token,
    get_person_by_name,
    init_db,
    lesson_gates,
    mandates_of_tickets,
    resolve_diagnosis_gate,
    resolve_epic_gate,
    resolve_lesson_gate,
    ship_checked,
    start_learning,
    start_session,
    tickets_by_mandate,
)
from claudarama.mirror import Gh, run_gh


def _run_claude(cmd: list[str], claude_binary: str) -> int:
    try:
        return subprocess.run(cmd).returncode
    except FileNotFoundError:
        print(f"Error: '{claude_binary}' executable not found in PATH.", file=sys.stderr)
        return 1


def mcp_config(host: str, port: int, token: str) -> str:
    url = f"http://{host}:{port}/mcp/{token}"
    return json.dumps({"mcpServers": {"claudarama": {"type": "http", "url": url}}})


def _review(gates: list[dict], describe, resolve, ask) -> bool:
    """Ask the CEO YES/NO/DISCUSS for each gate. True when any is left for discussion."""
    discuss = False
    for gate in gates:
        print(describe(gate))
        while (answer := ask("YES / NO / DISCUSS? ").strip().upper()) not in ("YES", "NO", "DISCUSS"):
            print("Please answer YES, NO or DISCUSS.")
        if answer == "DISCUSS":
            discuss = True
        else:
            resolve(gate["id"], answer == "YES")
    return discuss


def review_diagnosis_gates(db_path: Path, ask=input) -> bool:
    """Ask about each paused Diagnosis. True when any is left for discussion."""
    return _review(
        diagnosis_gates(db_path),
        lambda g: f"Diagnosis gate: mandate {g['id']!r}, diagnosis at {g['diagnosis_path']}",
        lambda mandate, ok: resolve_diagnosis_gate(db_path, mandate, ok),
        ask,
    )


def review_epic_gates(db_path: Path, ask=input) -> bool:
    """Ask about each paused Epic, listing its tickets. True when any is left for discussion."""
    return _review(
        epic_gates(db_path),
        lambda g: f"Epic gate: mandate {g['id']!r}, tickets:\n" + "\n".join(f"  - {t}" for t in g["tickets"]),
        lambda mandate, ok: resolve_epic_gate(db_path, mandate, ok),
        ask,
    )


def _open_prs(db_path: Path, gh: Gh) -> list[dict]:
    """Open PRs that close office tickets, each with the mandates they serve."""
    prs = json.loads(gh(["pr", "list", "--state", "open", "--json", "number,title,headRefOid,closingIssuesReferences"]))
    out = []
    for pr in prs:
        mandates = mandates_of_tickets(db_path, [str(i["number"]) for i in pr["closingIssuesReferences"]])
        if mandates:
            out.append({"id": pr["number"], "title": pr["title"], "head": pr["headRefOid"], "mandates": mandates})
    return out


def review_pr_gates(db_path: Path, gh: Gh = run_gh, ask=input) -> bool:
    """Ask about each open PR. YES merges, but only with a SHIP verdict on the head commit;
    NO closes it. True when any is left for discussion."""
    try:
        prs = {pr["id"]: pr for pr in _open_prs(db_path, gh)}
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"PR gate skipped: gh failed ({e}).", file=sys.stderr)
        return False

    def describe(g: dict) -> str:
        check = "SHIP" if ship_checked(db_path, g["id"], g["head"]) else "MISSING"
        return f"PR gate: #{g['id']} {g['title']!r} (mandates {', '.join(g['mandates'])}), Ship-check: {check}"

    def resolve(number: int, ok: bool) -> None:
        pr = prs[number]
        if not ok:
            gh(["pr", "close", str(number), "--comment", "Declined by the CEO at the PR gate."])
        elif not ship_checked(db_path, number, pr["head"]):
            print(f"Blocked: no SHIP verdict for head commit {pr['head'][:8]} of PR #{number}; not merged.")
        else:
            gh(["pr", "merge", str(number), "--merge", "--match-head-commit", pr["head"]])

    return _review(list(prs.values()), describe, resolve, ask)


def advance_to_learning(db_path: Path, gh: Gh = run_gh) -> None:
    """Move each unblocked EXECUTING mandate whose tickets are all closed on GitHub to LEARNING."""
    for mandate, tickets in tickets_by_mandate(db_path, "EXECUTING").items():
        try:
            closed = all(json.loads(gh(["issue", "view", t, "--json", "state"]))["state"] == "CLOSED" for t in tickets)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Cannot check tickets of {mandate!r}: gh failed ({e}).", file=sys.stderr)
            continue
        if closed:
            start_learning(db_path, mandate)


def review_lesson_gates(db_path: Path, ask=input) -> bool:
    """Ask about each paused Lesson. True when any is left for discussion."""
    return _review(
        lesson_gates(db_path),
        lambda g: f"Lesson gate: mandate {g['id']!r}, lessons at {g['lesson_path']}",
        lambda mandate, ok: resolve_lesson_gate(db_path, mandate, ok),
        ask,
    )


def open_ceo_session(
    host: str = "127.0.0.1",
    port: int = 8000,
    claude_binary: str = "claude",
    db_path: Path | None = None,
    pack_dir: Path | None = None,
) -> int:
    """Launch the CEO's Session: the owner token and the Assistant's brief."""
    db_path = db_path or get_office_db_path()
    init_db(db_path)
    if sys.stdin.isatty():  # DISCUSS leaves the gate paused for the session
        review_diagnosis_gates(db_path)
        review_epic_gates(db_path)
        review_pr_gates(db_path)
        advance_to_learning(db_path)
        review_lesson_gates(db_path)
    config = mcp_config(host, port, get_owner_token(db_path))
    brief = build_brief(pack_dir or Path.cwd() / ".claudarama", "assistant")
    return _run_claude([claude_binary, "--mcp-config", config, "--append-system-prompt", brief], claude_binary)


def talk_to_person(
    name: str,
    host: str = "127.0.0.1",
    port: int = 8000,
    claude_binary: str = "claude",
    db_path: Path | None = None,
    pack_dir: Path | None = None,
) -> int:
    """Interactive session with *name*: their token and brief; recorded open until it exits."""
    db_path = db_path or get_office_db_path()
    init_db(db_path)
    person = get_person_by_name(db_path, name)
    if person is None:
        print(f"Error: no person named '{name}'.", file=sys.stderr)
        return 1
    brief = build_brief(pack_dir or Path.cwd() / ".claudarama", person["role"])
    token = start_session(db_path, person["id"])
    cmd = [
        claude_binary,
        "--mcp-config", mcp_config(host, port, token),
        "--append-system-prompt", brief,
    ]
    try:
        return _run_claude(cmd, claude_binary)
    finally:
        end_session(db_path, token)
