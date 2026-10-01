"""The plugin door (issue #95): this repository as a Claude Code marketplace and plugin.

The plugin is read and driven the way Claude Code does it: the marketplace names the plugin,
the plugin's manifest declares the office server, and each skill renders by running the
command it injects.
"""
import asyncio
import json
import re
import shlex
import shutil
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from claudarama.cli import build_parser
from claudarama.db import (
    create_attach_code, create_turn_token, get_owner_token, get_turn, init_db, mark_turn_running, queue_turn,
)
from claudarama.gate import build_allowlist, decide
from claudarama.session import mcp_config

PLUGIN = Path(__file__).resolve().parent.parent  # the repository is the plugin's root
SKILLS = ("setup", "open", "status")  # /claudarama:<command>, one per terminal command the CEO uses


def _manifest() -> dict:
    return json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())


def _skill(name: str) -> tuple[dict[str, str], str]:
    """A skill's frontmatter and body."""
    text = (PLUGIN / "skills" / name / "SKILL.md").read_text()
    assert text.startswith("---\n")  # Claude Code reads frontmatter only from the file's first line
    front, _, body = text[4:].partition("\n---\n")
    return dict(line.split(": ", 1) for line in front.splitlines()), body


def _injected(name: str) -> str:
    """The one command Claude Code runs while it renders the skill; its output replaces the placeholder."""
    [command] = re.findall(r"^!`([^`]+)`$", _skill(name)[1], re.M)
    return command


@pytest.fixture
def env(tmp_path) -> dict[str, str]:
    """The CEO's machine as the plugin door needs it: `uv`, `git` and a signed-in `gh`, and nothing
    else of Claudarama's. The stand-in `gh` never reaches GitHub, the stand-in `claude` never starts
    a real turn, and the home directory is the test's own."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, code in (("gh", 0), ("claude", 1)):
        (bin_dir / name).write_text(f"#!/bin/sh\nexit {code}\n")
        (bin_dir / name).chmod(0o755)
    (bin_dir / "uv").symlink_to(shutil.which("uv"))
    cache = subprocess.run(["uv", "cache", "dir"], capture_output=True, text=True, check=True).stdout.strip()
    (tmp_path / "home").mkdir()
    # Sharing uv's cache keeps the run offline once the plugin's environment exists.
    return {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path / "home"), "UV_CACHE_DIR": cache}


def _render(name: str, project: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Render a skill the way Claude Code does: fill in the placeholder and run the injected
    command in the session's directory. What it prints is what the session reads."""
    command = _injected(name).replace("${CLAUDE_PLUGIN_ROOT}", str(PLUGIN))
    return subprocess.run(command, shell=True, cwd=project, env=env, capture_output=True, text=True)


# --- free check: the marketplace, the manifest and the skills resolve ---------------------


def test_the_repository_is_a_marketplace_whose_plugin_is_the_repository_itself():
    marketplace = json.loads((PLUGIN / ".claude-plugin" / "marketplace.json").read_text())
    assert marketplace["name"] and marketplace["owner"]["name"]
    [entry] = marketplace["plugins"]

    assert entry["source"].startswith("./")  # a relative source resolves from the marketplace root
    assert (PLUGIN / entry["source"]).resolve() == PLUGIN
    assert entry["name"] == _manifest()["name"] == "claudarama"  # so the skills are /claudarama:<command>


def test_each_plugin_skill_resolves_to_the_terminal_command_of_its_name():
    assert sorted(p.name for p in (PLUGIN / "skills").iterdir()) == sorted(SKILLS)
    for name in SKILLS:
        front, _ = _skill(name)
        command = _injected(name)
        program, *argv = shlex.split(command)

        assert program == "${CLAUDE_PLUGIN_ROOT}/bin/claudarama"  # the plugin's own copy of the terminal command
        assert build_parser().parse_args(argv).command == name
        # Outside auto mode, an injected command the skill does not pre-approve aborts the invocation.
        assert f"Bash({command})" in front["allowed-tools"].split(", ")
        assert front["description"]


def test_plugin_skills_are_invocable_by_the_user_only():
    for name in SKILLS:
        assert _skill(name)[0]["disable-model-invocation"] == "true"


# --- the skills run the terminal commands ---------------------------------------------------


def test_setup_from_the_plugin_scaffolds_the_pack_with_only_uv_on_the_machine(tmp_path, env):
    project = tmp_path / "project"
    project.mkdir()

    result = _render("setup", project, env)

    assert result.returncode == 0, result.stderr
    assert "Set up Claudarama pack" in result.stdout
    assert (project / ".claudarama" / "company.md").exists()


# --- /claudarama:open makes the session the CEO's Session -----------------------------------


@pytest.fixture
def project(tmp_path) -> Path:
    """A project with a pack whose charter is written."""
    project = tmp_path / "project"
    (project / ".claudarama").mkdir(parents=True)
    (project / ".claudarama" / "company.md").write_text("CHARTER-TEXT\n")
    return project


@asynccontextmanager
async def _serve(spec: dict, env: dict[str, str], cwd: Path):
    """An MCP client on the server process Claude Code starts from *spec*."""
    params = StdioServerParameters(command=spec["command"], args=spec["args"], env={**env, **spec.get("env", {})}, cwd=cwd)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            yield client


def _session(project: Path, env: dict[str, str], cwd: Path):
    """A Claude Code session on *project* with the plugin enabled: the office server process the
    plugin declares, started as Claude Code starts it, from whatever directory it happens to use."""
    fill = lambda s: s.replace("${CLAUDE_PLUGIN_ROOT}", str(PLUGIN)).replace("${CLAUDE_PROJECT_DIR}", str(project))
    [spec] = _manifest()["mcpServers"].values()
    return _serve({"command": fill(spec["command"]), "args": [fill(a) for a in spec["args"]]}, env, cwd)


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, 120))


def _open(project: Path, env: dict[str, str]) -> tuple[str, str]:
    """The CEO types /claudarama:open. Returns what the session reads, and the attach code in it."""
    result = _render("open", project, env)
    assert result.returncode == 0, result.stderr
    return result.stdout, re.search(r"^Attach code: (\S+)$", result.stdout, re.M).group(1)


def _office_db(env: dict[str, str]) -> Path | None:
    return next(Path(env["HOME"]).glob(".claudarama/*/office.db"), None)


def test_open_from_the_plugin_makes_the_session_the_ceos_and_loads_the_assistants_brief(tmp_path, project, env):
    async def session():
        async with _session(project, env, cwd=tmp_path) as office:
            before = await office.call_tool("whoami", {})
            untouched = _office_db(env) is None  # the plugin loads into every session; it creates nothing by itself
            brief, code = _open(project, env)
            attached = await office.call_tool("attach", {"code": code})
            return before, untouched, brief, attached, await office.call_tool("whoami", {})

    before, untouched, brief, attached, after = _run(session())

    assert before.isError and "token" in before.content[0].text
    assert untouched
    assert "You are the assistant (Nibbler)." in brief and "CHARTER-TEXT" in brief  # the same brief as the terminal door
    assert not attached.isError
    assert json.loads(after.content[0].text)["kind"] == "owner"


def test_the_office_runs_turns_once_the_session_is_attached_and_not_before(tmp_path, project, env):
    async def session():
        async with _session(project, env, cwd=tmp_path) as office:
            _, code = _open(project, env)
            db = _office_db(env)
            turn = queue_turn(db, "fullstack-engineer", kind="ritual")
            await asyncio.sleep(1)  # a running office would have launched it by now
            before = get_turn(db, turn)["status"]
            await office.call_tool("attach", {"code": code})
            while get_turn(db, turn)["status"] in ("queued", "running"):
                await asyncio.sleep(0.05)
            return before, get_turn(db, turn)["status"]

    # The stand-in `claude` exits at once, so a launched turn ends as failed.
    assert _run(session()) == ("queued", "failed")


def test_open_from_a_subdirectory_opens_the_same_office_with_the_same_brief(tmp_path, project, env):
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    (project / "src").mkdir()

    async def session():
        async with _session(project, env, cwd=tmp_path) as office:
            brief, code = _open(project / "src", env)
            return brief, await office.call_tool("attach", {"code": code})

    brief, attached = _run(session())

    assert "CHARTER-TEXT" in brief
    assert not attached.isError


def test_an_attach_code_comes_only_from_the_ceos_open_and_works_once(tmp_path, project, env):
    async def sessions():
        async with _session(project, env, cwd=tmp_path) as first, _session(project, env, cwd=tmp_path) as second:
            guessed = await first.call_tool("attach", {"code": "not-a-code"})
            untouched = _office_db(env) is None
            _, code = _open(project, env)
            await first.call_tool("attach", {"code": code})
            reused = await second.call_tool("attach", {"code": code})
            return guessed, untouched, reused, await second.call_tool("whoami", {})

    guessed, untouched, reused, second = _run(sessions())

    assert guessed.isError and "attach code" in guessed.content[0].text
    assert untouched
    assert reused.isError and "attach code" in reused.content[0].text
    assert second.isError  # the other session on the project is still nobody's


def test_a_server_handed_a_token_cannot_be_attached(tmp_path, env):
    """`attach` exists only on the server the plugin declares: a turn's server, and the one
    `claudarama open` passes from the terminal, already speak for their caller."""
    db = tmp_path / "office.db"
    init_db(db)
    turn = queue_turn(db, "fullstack-engineer", kind="ritual")
    mark_turn_running(db, turn)
    code = create_attach_code(db)

    async def tools(token: str) -> list[str]:
        [spec] = json.loads(mcp_config(db, token))["mcpServers"].values()
        async with _serve(spec, env, cwd=tmp_path) as office:
            assert (await office.call_tool("attach", {"code": code})).isError
            return [tool.name for tool in (await office.list_tools()).tools]

    for token in (create_turn_token(db, turn), get_owner_token(db)):
        names = _run(tools(token))
        assert "whoami" in names and "attach" not in names


# --- nothing the plugin adds reaches a specialist's turn -------------------------------------


def test_a_turn_cannot_use_what_the_plugin_adds(project):
    """An installed plugin also loads into headless runs. A turn is launched with only its own
    office server (``--strict-mcp-config``); these are the walls behind that."""
    allow, deny = build_allowlist(project / ".claudarama")
    [server] = _manifest()["mcpServers"]
    attach = f"mcp__plugin_{_manifest()['name']}_{server}__attach"  # how Claude Code names a plugin server's tool
    assert attach in _skill("open")[0]["allowed-tools"].split(", ")

    for tool, tool_input in (
        (attach, {"code": "any"}),
        ("Skill", {"skill": "claudarama:open"}),
        ("Bash", {"command": "claudarama open --attach"}),
        ("Bash", {"command": f"{PLUGIN}/bin/claudarama open --attach"}),
    ):
        allowed, reason = decide({"tool_name": tool, "tool_input": tool_input}, allow, deny)
        assert not allowed, f"{tool} {tool_input}: {reason}"


def test_the_plugin_declares_no_hooks():
    """A hook the plugin gains later runs in every session and every turn, so it must do nothing
    outside the CEO's Session. Until one is needed there is none."""
    assert "hooks" not in _manifest()
    assert not (PLUGIN / "hooks").exists()
