"""A real office for a scenario's steps: a temporary git repository, the office server, its turn
runner, its brief builder and its database. Only four edges are stand-ins (``stand_ins.py``):
``claude`` for each turn, ``gh``, the notification sink (``osascript``), and the CEO's answers.
"""
import asyncio
import contextlib
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

from claudarama.db import get_owner_token, get_turn, init_db, mandate_states, queue_turn
from claudarama.scaffold import PACK_DIR_NAME
from claudarama.scenario.stand_ins import RESULT, call
from claudarama.scenario.validator import CeoActionStep, Scenario
from claudarama.session import mcp_config

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
    subprocess.run(["git", "init", "--quiet", str(project)], check=True)
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

    # Each Role's scripted turns, in the order the scenario lists them: its stand-in takes the next one.
    scripts: dict[str, list[dict]] = {}
    for step in scenario.steps:
        for turn in turns_of(step):
            scripts.setdefault(turn["role"], []).append(turn)
    state.mkdir()
    for role, turns in scripts.items():
        (state / f"{role}.json").write_text(json.dumps(turns))

    def notifications() -> list[str]:
        """What the office has told the CEO on the desktop so far, as the stand-in sink kept it."""
        told = state / "notifications"
        return [json.loads(line) for line in told.read_text().splitlines()] if told.exists() else []

    told: list[str] = []  # the notifications already shown
    discussing: set[str] = set()  # gates the CEO left at DISCUSS: no new notification brings them back

    async def answer(reply: str, ceo: ClientSession) -> None:
        """The CEO's *reply* at the first gate that is waiting, given inside the Session through the
        office's owner-only gate tools; any other gate is left for a later step.

        The CEO learns that a gate opened from the office's notification, so the answer waits for one."""
        gates = json.loads((await ceo.call_tool("list_gates", {})).content[0].text)["gates"]
        if not gates:
            raise Stuck(f"the CEO answered {reply}, but no gate was waiting")
        gate = gates[0]
        if gate["gate"] not in discussing:
            try:
                await until(lambda: len(notifications()) > len(told))
            except Stuck:
                raise Stuck(f"the office sent no notification that the gate {gate['gate']!r} opened") from None
            new = notifications()[len(told):]
            told.extend(new)
            seen.extend(f"Notification: {text}" for text in new)
        seen.append(gate["shows"])
        answered = await ceo.call_tool("answer_gate", {"gate": gate["gate"], "answer": reply})
        seen.append(f"CEO answers {reply}" + (f" -> REFUSED: {answered.content[0].text}" if answered.isError else ""))
        (discussing.add if reply == "DISCUSS" else discussing.discard)(gate["gate"])

    def transcript(turn_id: str) -> str:
        path = db.parent / "turns" / f"{turn_id}.jsonl"  # where the Session's server keeps it
        return path.read_text().rstrip() if path.exists() else ""

    def ended(turn_id: str) -> bool:
        """`send` marks a turn done while it is still running, so a done turn has ended only once its transcript has."""
        status = get_turn(db, turn_id)["status"]
        return status in ("failed", "refused") or (status == "done" and transcript(turn_id).endswith(RESULT))

    async def take(step, ceo: ClientSession) -> None:
        if isinstance(step, CeoActionStep):
            for asked in step.calls:
                seen.append(await call(ceo, "CEO", asked["tool"], asked.get("args", {})))
            if step.input:
                await answer(step.input, ceo)
        else:
            # ponytail: the scenario wakes each scripted turn itself; drop this once the office wakes them (#89, #90).
            woken = [
                (turn["role"], queue_turn(db, turn["role"], thread=f"ticket:{turn['ticket']}" if "ticket" in turn else None))
                for turn in turns_of(step)
            ]
            await until(lambda: all(ended(turn_id) for _, turn_id in woken), timeout=60)
            for role, turn_id in woken:
                turn = get_turn(db, turn_id)
                if shown := transcript(turn_id).removesuffix(RESULT).rstrip():
                    seen.append(shown)
                seen.append(f"{role}'s turn: " + ": ".join(filter(None, (turn["status"], turn["refusal"], turn["error"]))))
        seen.extend(
            f"Mandate {m['id']!r}: {m['status']}" + (", waiting for the CEO" if m["blocked_on_ceo"] else "")
            for m in mandate_states(db)
        )

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
