"""The stand-ins a scenario's office runs in place of ``claude`` and ``gh``.

Run by path, so a turn starts without loading the office: ``stand_ins.py <claude|gh> <state
directory> <the arguments the real program was given>``. The state directory holds each Role's
scripted turns (``<role>.json``) and the stand-in GitHub (``gh.json``).
"""
import asyncio
import json
import os
import re
import shlex
import subprocess
import sys
import textwrap
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

RESULT = '{"type": "result"}'  # the last line of a turn's transcript, as of claude's own
FIRST_PULL_REQUEST = 101  # clear of the scenario's ticket numbers; GitHub numbers both from one counter


async def call(office: ClientSession, who: str, tool: str, args: dict) -> str:
    """Call one of the office's tools as *who*; the line to show for it: the call and its answer, or its refusal."""
    result = await office.call_tool(tool, args)
    text = result.content[0].text if result.content else ""
    try:
        text = json.dumps(json.loads(text))  # on one line
    except ValueError:
        pass
    return f"{who} calls {tool} {json.dumps(args)} -> {'REFUSED: ' if result.isError else ''}{text}"


async def claude(state: Path, argv: list[str]) -> None:
    """One turn: start the office server this launch was handed, learn from it which Role this is,
    and carry out that Role's next scripted turn."""
    spec = json.loads(argv[argv.index("--mcp-config") + 1])["mcpServers"]["claudarama"]
    server = StdioServerParameters(command=spec["command"], args=spec["args"], env={**os.environ, **spec["env"]})
    async with stdio_client(server) as (read, write), ClientSession(read, write) as office:
        await office.initialize()
        role = json.loads((await office.call_tool("whoami", {})).content[0].text)["person_id"]
        script = state / f"{role}.json"
        turns = json.loads(script.read_text()) if script.exists() else []
        if not turns:
            sys.exit(f"no scripted turn is left for the {role}")
        script.write_text(json.dumps(turns[1:]))
        print(f"{role}'s brief:\n" + textwrap.indent(argv[argv.index("-p") + 1], "  | "), flush=True)
        for step in turns[0]["calls"]:
            if "run" in step:
                done = subprocess.run(step["run"], capture_output=True, text=True)
                print(f"{role} runs {shlex.join(step['run'])} -> {(done.stdout + done.stderr).strip()}", flush=True)
            else:
                print(await call(office, role, step["tool"], step.get("args", {})), flush=True)
        print(RESULT, flush=True)


def gh(state: Path, argv: list[str]) -> None:
    """A GitHub of milestones, issues and pull requests, kept in ``gh.json``. It answers what the
    office and its turns ask of ``gh`` and nothing else."""
    # ponytail: no lock on gh.json; add one when two turns of one step both script gh.
    path = state / "gh.json"
    hub = json.loads(path.read_text()) if path.exists() else {"milestones": [], "issues": {}, "prs": []}

    def issue(number: str) -> dict:
        return hub["issues"].setdefault(number, {"state": "OPEN", "milestone": None})

    def pr(number: str) -> dict:
        return hub["prs"][int(number) - FIRST_PULL_REQUEST]

    match argv:
        case ["api", "repos/{owner}/{repo}/milestones?state=all", *_]:
            print("\n".join(hub["milestones"]))
        case ["api", "repos/{owner}/{repo}/milestones", "-f", title]:
            hub["milestones"].append(title.removeprefix("title="))
        case ["issue", "view", number, "--json", field]:
            print(json.dumps({field: issue(number)[field]}))
        case ["issue", "edit", number, "--milestone", milestone]:
            issue(number)["milestone"] = {"title": milestone}
        case ["issue", "close", number]:
            issue(number)["state"] = "CLOSED"
        case ["pr", "create", *flags]:
            given = dict(zip(flags[::2], flags[1::2]))
            number = FIRST_PULL_REQUEST + len(hub["prs"])
            hub["prs"].append({
                "number": number, "title": given["--title"], "state": "OPEN",
                "headRefOid": f"commit-{number}",  # the stand-in knows no git; a scripted Ship-check names this
                "closingIssuesReferences": [{"number": int(n)} for n in re.findall(r"#(\d+)", given.get("--body", ""))],
            })
            print(f"https://github.com/office/project/pull/{number}")
        case ["pr", "list", "--state", "open", *_]:
            print(json.dumps([p for p in hub["prs"] if p["state"] == "OPEN"]))
        case ["pr", "merge", number, "--merge", "--match-head-commit", head]:
            if pr(number)["headRefOid"] != head:
                sys.exit(f"head commit of #{number} is not {head}")
            pr(number)["state"] = "MERGED"
            for closed in pr(number)["closingIssuesReferences"]:
                issue(str(closed["number"]))["state"] = "CLOSED"
        case ["pr", "close", number, *_]:
            pr(number)["state"] = "CLOSED"
        case _:
            sys.exit(f"the stand-in gh has no answer for: gh {shlex.join(argv)}")
    path.write_text(json.dumps(hub))


if __name__ == "__main__":
    program, state, argv = sys.argv[1], Path(sys.argv[2]), sys.argv[3:]
    if program == "claude":
        asyncio.run(claude(state, argv))
    else:
        gh(state, argv)
