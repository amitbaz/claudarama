import json
import subprocess
import sys
from pathlib import Path

from claudarama.brief import build_brief
from claudarama.db import (
    create_attach_code,
    diagnosis_gates,
    epic_gates,
    get_office_db_path,
    get_owner_token,
    get_project_root,
    init_db,
    lesson_gates,
    mandates_of_tickets,
    one_line,
    resolve_diagnosis_gate,
    resolve_epic_gate,
    resolve_lesson_gate,
    ship_checked,
    shown,
    start_learning,
    ticket_author,
    tickets_by_mandate,
    wake,
)
from claudarama.mirror import Gh, run_gh
from claudarama.scaffold import PACK_DIR_NAME


def _run_claude(cmd: list[str], claude_binary: str) -> int:
    try:
        return subprocess.run(cmd).returncode
    except FileNotFoundError:
        print(f"Error: '{claude_binary}' executable not found in PATH.", file=sys.stderr)
        return 1


TOKEN_ENV = "CLAUDARAMA_TOKEN"  # the secret that names the server process's caller
DB_ENV = "CLAUDARAMA_DB"  # the office's database, shared by every server process


def mcp_config(db_path: Path, token: str) -> str:
    """Config that has Claude Code start the office server as its own process, speaking for *token*."""
    server = {
        "command": sys.executable,
        "args": ["-m", "claudarama.daemon"],
        "env": {TOKEN_ENV: token, DB_ENV: str(Path(db_path).resolve())},  # a turn runs in another directory
    }
    return json.dumps({"mcpServers": {"claudarama": server}})


def _review(gates: list[dict], describe, resolve, ask) -> bool:
    """Ask the CEO YES/NO/DISCUSS for each gate, and a one-line reason for a NO.
    True when any is left for discussion."""
    discuss = False
    for gate in gates:
        print(describe(gate))
        while (answer := ask("YES / NO / DISCUSS? ").strip().upper()) not in ("YES", "NO", "DISCUSS"):
            print("Please answer YES, NO or DISCUSS.")
        if answer == "DISCUSS":
            discuss = True
            continue
        reason = ""
        while answer == "NO" and not (reason := ask("Why not, in one line? ").strip()):
            print("A NO needs a reason: it goes to whoever produced the work.")
        resolve(gate["id"], answer == "YES", reason)
    return discuss


def describe_diagnosis_gate(gate: dict) -> str:
    """What the CEO is shown at a Diagnosis gate: the Diagnosis, and beside it its Challenge."""
    challenge = (  # a Diagnosis that was paused here before Challenges existed has none
        f"Challenge by {shown(gate['challenger'])}: {gate['verdict']}: {gate['reasons']}\nWhat was run: {gate['ran']}"
        if gate["verdict"] else "Challenge: none recorded"
    )
    return f"Diagnosis gate: mandate {gate['id']!r}, diagnosis at {gate['diagnosis_path']}\n{challenge}"


def review_diagnosis_gates(db_path: Path, ask=input) -> bool:
    """Ask about each paused Diagnosis, shown with its Challenge. True when any is left for discussion."""
    return _review(
        diagnosis_gates(db_path),
        describe_diagnosis_gate,
        lambda mandate, ok, reason: resolve_diagnosis_gate(db_path, mandate, ok, reason),
        ask,
    )


def review_epic_gates(db_path: Path, ask=input) -> bool:
    """Ask about each paused Epic, listing its tickets. True when any is left for discussion."""
    return _review(
        epic_gates(db_path),
        lambda g: f"Epic gate: mandate {g['id']!r}, tickets:\n" + "\n".join(f"  - {t}" for t in g["tickets"]),
        lambda mandate, ok, reason: resolve_epic_gate(db_path, mandate, ok, reason),
        ask,
    )


def _open_prs(db_path: Path, gh: Gh) -> list[dict]:
    """Open PRs that close office tickets, each with the mandates they serve."""
    prs = json.loads(gh(["pr", "list", "--state", "open", "--json", "number,title,headRefOid,closingIssuesReferences"]))
    out = []
    for pr in prs:
        tickets = [str(i["number"]) for i in pr["closingIssuesReferences"]]
        mandates = mandates_of_tickets(db_path, tickets)
        if mandates:
            out.append({
                "id": pr["number"], "title": pr["title"], "head": pr["headRefOid"], "mandates": mandates, "tickets": tickets,
            })
    return out


def review_pr_gates(db_path: Path, gh: Gh = run_gh, ask=input) -> bool:
    """Ask about each open PR. YES merges, but only with a SHIP verdict on the head commit;
    NO closes it and wakes whoever worked on its tickets with the CEO's reason. True when any is
    left for discussion."""
    try:
        prs = {pr["id"]: pr for pr in _open_prs(db_path, gh)}
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"PR gate skipped: gh failed ({e}).", file=sys.stderr)
        return False

    def describe(g: dict) -> str:
        check = "SHIP" if ship_checked(db_path, g["id"], g["head"]) else "MISSING"
        return f"PR gate: #{g['id']} {g['title']!r} (mandates {', '.join(g['mandates'])}), Ship-check: {check}"

    def resolve(number: int, ok: bool, reason: str) -> None:
        pr = prs[number]
        if not ok:
            no = f"PR gate: {one_line(reason)}"
            gh(["pr", "close", str(number), "--comment", "Declined by the CEO at the PR gate."])
            for ticket in pr["tickets"]:
                if author := ticket_author(db_path, ticket):
                    wake(db_path, author, ticket, no)
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
        lambda mandate, ok, reason: resolve_lesson_gate(db_path, mandate, ok, reason),
        ask,
    )


def review_gates(db_path: Path, gh: Gh = run_gh, ask=input) -> None:
    """Ask the CEO about every gate that is waiting, in the order of the loop."""
    review_diagnosis_gates(db_path, ask)
    review_epic_gates(db_path, ask)
    review_pr_gates(db_path, gh, ask)
    advance_to_learning(db_path, gh)
    review_lesson_gates(db_path, ask)


def open_ceo_session(
    claude_binary: str = "claude", db_path: Path | None = None, pack_dir: Path | None = None,
    attach: bool = False,
) -> int:
    """Open the office: the CEO's Session, with the Assistant's brief and the office server
    holding the owner token.

    From the terminal this launches the Session. With *attach* (the plugin door) the Session
    is the Claude Code session this runs in: it prints the brief for that session to read, and
    the code with which the session makes the office server the plugin declared the owner's.
    """
    db_path = db_path or get_office_db_path()
    init_db(db_path)
    # The pack of the main checkout, where the Session's server finds it, from any subdirectory or worktree.
    brief = build_brief(pack_dir or get_project_root() / PACK_DIR_NAME, "assistant")
    if attach:
        print(f"{brief}\n\nAttach code: {create_attach_code(db_path)}")
        return 0
    if sys.stdin.isatty():  # DISCUSS leaves the gate paused for the session
        review_gates(db_path)
    config = mcp_config(db_path, get_owner_token(db_path))
    return _run_claude([claude_binary, "--mcp-config", config, "--append-system-prompt", brief], claude_binary)
