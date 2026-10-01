"""A real office for a scenario's steps: a temporary git repository, the office server, its turn
runner, its brief builder and its database. Only four edges are stand-ins (``stand_ins.py``):
``claude`` for each turn, ``gh``, the notification sink (``osascript``), and the CEO's answers.
"""
import asyncio
import contextlib
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from claudarama.db import get_owner_token, get_turn, init_db, list_turns, mandate_states
from claudarama.scaffold import PACK_DIR_NAME
from claudarama.scenario.stand_ins import RESULT, call
from claudarama.scenario.validator import CeoActionStep, Scenario
from claudarama.session import mcp_config, review_gates
from claudarama.worktrees import worktrees_root

STAND_INS = Path(__file__).with_name("stand_ins.py")


class Stuck(Exception):
    """The office did not get to where a step needed it."""


def script(path: Path, body: str) -> Path:
    """An executable shell script at *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)
    return path


def project(root: Path, name: str, org_yaml: str = "") -> tuple[Path, Path]:
    """A project in its own git repository with a pack, and its office's database under ``root/home``."""
    project = root / name
    (project / PACK_DIR_NAME).mkdir(parents=True)
    (project / PACK_DIR_NAME / "org.yaml").write_text(org_yaml)
    subprocess.run(["git", "init", "--quiet", "--initial-branch=main", str(project)], check=True)
    subprocess.run(  # a ticket's worktree starts from a commit
        ["git", "-C", str(project), "-c", "user.name=CEO", "-c", "user.email=ceo@example.com",
         "commit", "--quiet", "--allow-empty", "-m", "Start"],
        check=True,
    )
    db = root / "home" / ".claudarama" / name / "office.db"
    init_db(db)
    return project, db


@contextlib.asynccontextmanager
async def session(project: Path, db: Path, bin_dir: Path):
    """The CEO's Session on *project*: the office server process Claude Code starts for it.

    The programs in *bin_dir* come first on its ``PATH``, and its home is the one the database is under.
    """
    spec = json.loads(mcp_config(db, get_owner_token(db)))["mcpServers"]["claudarama"]
    env = {**spec["env"], "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "HOME": str(db.parents[2])}
    params = StdioServerParameters(command=spec["command"], args=spec["args"], env=env, cwd=project)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            yield client


async def until(condition, timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() >= deadline:
            raise Stuck("timed out waiting on the office")
        await asyncio.sleep(0.05)


async def _walk(scenario: Scenario, root: Path, seen: list[str]) -> str | None:
    """Take each step in turn, adding what the office shows to *seen*. Returns why it stopped short, if it did."""
    office, db = project(root, "office")
    bin_dir, state = root / "bin", root / "stand-ins"
    for program in ("claude", "gh", "osascript"):
        script(bin_dir / program, shlex.join(["exec", sys.executable, str(STAND_INS), program, str(state)]) + ' "$@"')

    def turns_of(step) -> list[dict]:
        return [{"role": scenario.role, **turn} for turn in getattr(step, "turns", [])]

    # Each Role's scripted turns, in the order the scenario lists them: its stand-in takes the next one,
    # and acts on it once the walk reaches the turn's step and leaves its `go` file. The office may
    # start the turn earlier, at the step that woke it.
    scripts: dict[str, list[dict]] = {}
    for step in scenario.steps:
        for turn in turns_of(step):
            scripts.setdefault(turn["role"], []).append(turn)
    state.mkdir()
    for role, turns in scripts.items():
        (state / f"{role}.json").write_text(json.dumps([{**turn, "go": f"{role}.{n}.go"} for n, turn in enumerate(turns)]))
    reached: dict[str, int] = {}  # how many of each Role's scripted turns the walk has reached

    def notifications() -> list[str]:
        """What the office has told the CEO on the desktop so far, as the stand-in sink kept it."""
        told = state / "notifications"
        return [json.loads(line) for line in told.read_text().splitlines()] if told.exists() else []

    told: list[str] = []  # the notifications already shown

    def gh(args: list[str]) -> str:
        return subprocess.run([bin_dir / "gh", *args], check=True, capture_output=True, text=True).stdout

    def answer(reply: str, reason: str) -> None:
        """The CEO's *reply* at the first gate that is waiting, with the *reason* a NO is asked for;
        any other gate is left for a later step."""
        scripted = [(reply, f"CEO answers {reply}")] + [(reason, f"CEO's reason: {reason}")] * (reply == "NO")
        replies = []

        def ask(_question: str) -> str:
            said, line = scripted.pop(0) if scripted else ("DISCUSS", "CEO answers DISCUSS")
            replies.append(said)
            print(line)
            return said

        shown = io.StringIO()
        with contextlib.redirect_stdout(shown):
            review_gates(db, office, gh, ask)
        seen.extend(shown.getvalue().splitlines())
        if not replies:
            raise Stuck(f"the CEO answered {reply}, but no gate was waiting")

    def transcript(turn_id: str) -> str:
        path = db.parent / "turns" / f"{turn_id}.jsonl"  # where the Session's server keeps it
        return path.read_text().rstrip() if path.exists() else ""

    def ended(turn_id: str) -> bool:
        """`send` marks a turn done while it is still running, so a done turn has ended only once its transcript has."""
        status = get_turn(db, turn_id)["status"]
        return status in ("failed", "refused") or (status == "done" and transcript(turn_id).endswith(RESULT))

    listed: set[str] = set()  # the turns already shown as woken
    woken: dict[tuple, list[str]] = {}  # by Role and thread: the turns the office queued that no scripted turn has taken

    def where(thread: str | None) -> str:
        return (thread or "no thread").replace(":", " ", 1)

    async def take(step, ceo: ClientSession) -> None:
        if isinstance(step, CeoActionStep):
            for asked in step.calls:
                seen.append(await call(ceo, "CEO", asked["tool"], asked.get("args", {})))
            if step.input:
                answer(step.input, step.reason)
        else:
            taken = []
            for turn in turns_of(step):
                thread = f"ticket:{turn['ticket']}" if "ticket" in turn else None
                if not (waiting := woken.get((turn["role"], thread))):
                    raise Stuck(f"the office did not wake the {turn['role']} on {where(thread)}")
                taken.append((turn["role"], waiting.pop(0)))
                (state / f"{turn['role']}.{reached.get(turn['role'], 0)}.go").touch()
                reached[turn["role"]] = reached.get(turn["role"], 0) + 1
            await until(lambda: all(ended(turn_id) for _, turn_id in taken), timeout=60)
            for role, turn_id in taken:
                turn = get_turn(db, turn_id)
                if shown := transcript(turn_id).removesuffix(RESULT).rstrip():
                    seen.append(shown)
                seen.append(f"{role}'s turn: " + ": ".join(filter(None, (turn["status"], turn["refusal"], turn["error"]))))
        for turn in list_turns(db):  # the turns the office queued during this step
            if turn["id"] not in listed:
                listed.add(turn["id"])
                woken.setdefault((turn["person_id"], turn["thread"]), []).append(turn["id"])
                seen.append(f"{turn['person_id']} is woken on {where(turn['thread'])}")
        new = notifications()[len(told):]
        told.extend(new)
        seen.extend(f"Notification: {text}" for text in new)
        seen.extend(
            f"Mandate {m['id']!r}: {m['status']}" + (", waiting for the CEO" if m["blocked_on_ceo"] else "")
            for m in mandate_states(db)
        )
        on = subprocess.run(["git", "-C", str(office), "branch", "--show-current"], capture_output=True, text=True)
        worktrees = sorted(path.name for path in worktrees_root(office).glob("*"))
        seen.append(f"The CEO's checkout is on {on.stdout.strip()}; worktrees: {', '.join(worktrees) or 'none'}")

    async with session(office, db, bin_dir) as ceo:
        try:
            for step in scenario.steps:
                await take(step, ceo)
        except Stuck as e:
            return str(e)


def run_office(scenario: Scenario) -> tuple[str, str | None]:
    """Walk *scenario*'s steps through a real office in a temporary git repository.

    Returns what the office showed, a line per event, and why the walk stopped short when it did.
    """
    seen: list[str] = []
    with tempfile.TemporaryDirectory() as root:
        stuck = asyncio.run(_walk(scenario, Path(root).resolve(), seen))
    return "\n".join(seen) + "\n", stuck
