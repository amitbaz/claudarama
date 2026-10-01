import json
import sqlite3
import subprocess
import sys
import time
from functools import partial
from pathlib import Path
from typing import Iterator

from claudarama.brief import build_brief
from claudarama.db import (
    ceo_messages,
    create_attach_code,
    diagnosis_gates,
    epic_gates,
    get_office_db_path,
    get_owner_token,
    get_project_root,
    init_db,
    is_new_head,
    lesson_gates,
    mandates_of_tickets,
    mark_shown,
    one_line,
    pauses,
    resolve_diagnosis_gate,
    resolve_epic_gate,
    resolve_lesson_gate,
    ship_checked,
    shipped,
    shown,
    start_learning,
    ticket_role,
    tickets_by_mandate,
    wake,
)
from claudarama.mirror import Gh, run_gh
from claudarama.scaffold import PACK_DIR_NAME
from claudarama.worktrees import remove_finished_worktrees


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
        try:
            resolve(gate["id"], answer == "YES", reason)
        except PermissionError as e:
            print(f"Blocked: {e}.")
    return discuss


# Each kind of gate is its waiting gates, what the CEO is shown of one, and how an answer resolves it.


def _describe_diagnosis(gate: dict) -> str:
    """The Diagnosis, and beside it its Challenge."""
    challenge = (  # a Diagnosis that was paused here before Challenges existed has none
        f"Challenge by {shown(gate['challenger'])}: {gate['verdict']}: {gate['reasons']}\nWhat was run: {gate['ran']}"
        if gate["verdict"] else "Challenge: none recorded"
    )
    return f"Diagnosis gate: mandate {gate['id']!r}, diagnosis at {gate['diagnosis_path']}\n{challenge}"


def _diagnosis(db_path: Path):
    return (
        diagnosis_gates(db_path),
        _describe_diagnosis,
        lambda mandate, ok, reason: resolve_diagnosis_gate(db_path, mandate, ok, reason),
    )


def _epic(db_path: Path):
    return (
        epic_gates(db_path),
        lambda g: f"Epic gate: mandate {g['id']!r}, tickets:\n"
        + "\n".join(f"  - {ticket}: {shown(role)}" for ticket, role in g["tickets"].items()),
        lambda mandate, ok, reason: resolve_epic_gate(db_path, mandate, ok, reason),
    )


def _lesson(db_path: Path):
    return (
        lesson_gates(db_path),
        lambda g: f"Lesson gate: mandate {g['id']!r}, Retro at {g['lesson_path']}, Lessons:\n"
        + ("\n".join(f"  - {shown(lesson['scope'])}: {lesson['text']}" for lesson in g["lessons"]) or "  none"),
        lambda mandate, ok, reason: resolve_lesson_gate(db_path, mandate, ok, reason),
    )


def review_diagnosis_gates(db_path: Path, ask=input) -> bool:
    """Ask about each paused Diagnosis, shown with its Challenge. True when any is left for discussion."""
    return _review(*_diagnosis(db_path), ask)


def review_epic_gates(db_path: Path, ask=input) -> bool:
    """Ask about each paused Epic, listing each ticket and its Role. True when any is left for discussion."""
    return _review(*_epic(db_path), ask)


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


def _pr(db_path: Path, gh: Gh):
    """YES merges, but only with a SHIP verdict on the head commit; NO closes the PR and wakes the
    Role of each ticket it closes with the CEO's reason. No gates when gh fails."""
    try:
        prs = {pr["id"]: pr for pr in _open_prs(db_path, gh)}
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"PR gate skipped: gh failed ({e}).", file=sys.stderr)
        prs = {}

    def describe(g: dict) -> str:
        check = "SHIP" if ship_checked(db_path, g["id"], g["head"]) else "MISSING"
        return f"PR gate: #{g['id']} {g['title']!r} (mandates {', '.join(g['mandates'])}), Ship-check: {check}"

    def resolve(number: int, ok: bool, reason: str) -> None:
        pr = prs[number]
        if not ok:
            no = f"PR gate: {one_line(reason)}"
            gh(["pr", "close", str(number), "--comment", "Declined by the CEO at the PR gate."])
            for ticket in pr["tickets"]:
                if role := ticket_role(db_path, ticket):
                    wake(db_path, role, ticket, no)
        elif not ship_checked(db_path, number, pr["head"]):
            raise PermissionError(f"no SHIP verdict for head commit {pr['head'][:8]} of PR #{number}; not merged")
        else:
            gh(["pr", "merge", str(number), "--merge", "--match-head-commit", pr["head"]])

    return list(prs.values()), describe, resolve


def review_pr_gates(db_path: Path, gh: Gh = run_gh, ask=input) -> bool:
    """Ask about each open PR. True when any is left for discussion."""
    return _review(*_pr(db_path, gh), ask)


def open_gates(db_path: Path, gh: Gh | None = run_gh) -> list[dict]:
    """Every gate waiting for the CEO, in the order of the loop: its name (``gate``), what the CEO
    is shown (``shows``) and how a YES or NO resolves it (``resolve(approved, reason)``; a NO
    needs its one-line reason). No PR gates without *gh*."""
    kinds = [("diagnosis", _diagnosis(db_path)), ("epic", _epic(db_path))]
    kinds += [("pr", _pr(db_path, gh))] if gh else []
    kinds += [("lesson", _lesson(db_path))]
    return [
        {"gate": f"{kind}:{g['id']}", "shows": describe(g), "resolve": partial(resolve, g["id"])}
        for kind, (gates, describe, resolve) in kinds
        for g in gates
    ]


def waiting(db_path: Path) -> dict[tuple, str]:
    """What the CEO is told of each gate, read from the office's own records alone, so asking again
    and again costs no call to GitHub. A PR gate counts from the SHIP verdict on its head commit:
    that is when the office starts to wait on the CEO.

    Keyed by the gate's opening, so a gate that closed and opened again is another one."""
    paused = pauses(db_path)
    kinds = (_diagnosis(db_path), _epic(db_path), _lesson(db_path))
    told = {(text := describe(g), paused.get(g["id"])): text for gates, describe, _ in kinds for g in gates}
    return told | {
        (pr, head): f"PR gate: #{pr} has a SHIP verdict for head commit {head[:8]}" for pr, head in shipped(db_path)
    }


def watch_gates(db_path: Path, poll: float = 0.5) -> Iterator[str]:
    """Each gate as it opens, for as long as the caller keeps asking. Gates open at the start are not news."""
    known = set(waiting(db_path))
    while True:
        time.sleep(poll)
        try:
            now = waiting(db_path)
        except sqlite3.Error:  # the database is busy: ask again
            continue
        yield from (told for opening, told in now.items() if opening not in known)
        known = set(now)


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


def follow_github(db_path: Path, gh: Gh = run_gh) -> None:
    """What the office does about GitHub while it runs: wake the engineering-lead on each pull
    request that opened for a ticket or took a new push, and start the Learn step of each mandate
    whose tickets are all closed."""
    # ponytail: asks GitHub for every open PR and every ticket of an EXECUTING mandate each time a
    # turn ends; remember what is already closed if that gets slow.
    try:
        prs = _open_prs(db_path, gh)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Cannot look for pull requests: gh failed ({e}).", file=sys.stderr)
        prs = []
    for pr in prs:
        if is_new_head(db_path, pr["id"], pr["head"]):
            for ticket in pr["tickets"]:
                if mandates_of_tickets(db_path, [ticket]):  # a pull request may also close tickets that are not the office's
                    wake(db_path, "engineering-lead", ticket)
    advance_to_learning(db_path, gh)


def review_lesson_gates(db_path: Path, ask=input) -> bool:
    """Ask about each paused Lesson. True when any is left for discussion."""
    return _review(*_lesson(db_path), ask)


def review_gates(db_path: Path, project: Path, gh: Gh = run_gh, ask=input) -> None:
    """Ask the CEO about every gate that is waiting, in the order of the loop. *project* is the main checkout."""
    review_diagnosis_gates(db_path, ask)
    review_epic_gates(db_path, ask)
    review_pr_gates(db_path, gh, ask)
    remove_finished_worktrees(project, db_path, gh)  # of the tickets just merged or closed
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
    if messages := ceo_messages(db_path):  # everything sent to the CEO since the last open, together
        brief += "\n\n---\n\n## Messages for the CEO\n\n" + "\n".join(
            f"- {shown(m['sender'])}, {m['msg_type']} on {m['thread']}: {m['body']}" for m in messages
        )
    if attach:
        print(f"{brief}\n\nAttach code: {create_attach_code(db_path)}")
        code = 0
    else:
        if sys.stdin.isatty():  # DISCUSS leaves the gate paused for the session
            review_gates(db_path, get_project_root())
        config = mcp_config(db_path, get_owner_token(db_path))
        code = _run_claude([
            claude_binary, "--mcp-config", config,
            # The Assistant starts the watcher again each time it ends, whether or not the CEO is there to approve it.
            "--allowedTools", "Bash(claudarama watch)",
            # Last, after a flag that takes one value: the two above take as many as follow them.
            "--append-system-prompt", brief,
            "The CEO opened the office.",  # a first prompt: without one the Assistant waits to be spoken to
        ], claude_binary)
    if code == 0:  # a Session that never started showed nothing: the messages stay for the next open
        mark_shown(db_path, messages)
    return code
