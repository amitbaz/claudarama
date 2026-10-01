import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from claudarama.gate import build_allowlist
from claudarama.supervisor import load_org_settings

SRC = str(Path(__file__).resolve().parent.parent / "src")


def fake_gh(bin_dir: Path, exit_code: int | None) -> None:
    """Put a `gh` on bin_dir that exits with exit_code (None = no gh at all)."""
    bin_dir.mkdir(exist_ok=True)
    if exit_code is not None:
        gh = bin_dir / "gh"
        gh.write_text(f"#!/bin/sh\nexit {exit_code}\n")
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)


def run_setup(tmp_path: Path, gh_exit: int | None = 0, *args: str) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    fake_gh(bin_dir, gh_exit)
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    env = {**os.environ, "PATH": str(bin_dir), "PYTHONPATH": SRC}
    return subprocess.run(
        [sys.executable, "-m", "claudarama", *(args or ("setup",))],
        cwd=project, capture_output=True, text=True, env=env,
    )


def top_keys(text: str) -> list[str]:
    return [
        line.partition(":")[0] for line in text.splitlines()
        if line and line[0] not in " \t#-" and ":" in line
    ]


def test_setup_scaffolds_pack(tmp_path: Path):
    result = run_setup(tmp_path)
    assert result.returncode == 0, result.stderr
    pack = tmp_path / "project" / ".claudarama"
    for name in ("company.md", "org.yaml", "gates.yaml", "stack.yaml"):
        assert (pack / name).stat().st_size > 0
    dirs = {p.relative_to(pack).as_posix() for p in pack.rglob("*") if p.is_dir()}
    assert dirs == {"profiles", "scenarios", "company", "company/diagnoses", "company/retros"}
    assert "departments" not in (pack / "org.yaml").read_text()


def test_setup_keeps_existing_pack(tmp_path: Path):
    pack = tmp_path / "project" / ".claudarama"
    pack.mkdir(parents=True)
    (pack / "custom.txt").write_text("user content")
    result = run_setup(tmp_path)
    assert result.returncode == 0
    assert "already exists" in result.stdout
    assert (pack / "custom.txt").read_text() == "user content"
    assert not (pack / "org.yaml").exists()


def test_init_is_gone(tmp_path: Path):
    result = run_setup(tmp_path, 0, "init")
    assert result.returncode == 2
    assert not (tmp_path / "project" / ".claudarama").exists()


def test_setup_without_gh_names_the_fix(tmp_path: Path):
    result = run_setup(tmp_path, None)
    assert result.returncode == 1
    assert "gh" in result.stderr and "install" in result.stderr.lower()
    assert not (tmp_path / "project" / ".claudarama").exists()


def test_setup_signed_out_names_the_fix(tmp_path: Path):
    result = run_setup(tmp_path, 1)
    assert result.returncode == 1
    assert "gh auth login" in result.stderr
    assert not (tmp_path / "project" / ".claudarama").exists()


# --- free check: every key the scaffold writes is one the code reads -----------------


@pytest.fixture
def pack(tmp_path: Path) -> Path:
    assert run_setup(tmp_path).returncode == 0
    return tmp_path / "project" / ".claudarama"


def test_every_org_key_is_read(pack: Path):
    keys = top_keys((pack / "org.yaml").read_text())
    assert keys
    for key in keys:
        def settings(value: str):
            probe = pack / f"probe-{key}"
            probe.mkdir(exist_ok=True)
            (probe / "org.yaml").write_text(f"{key}: {value}\n")
            return load_org_settings(probe)

        # a key is read when some value changes what the code sees, compared to a value it cannot parse
        baseline = settings("")
        assert any(settings(v) != baseline for v in ("7", "true", "zzz")), f"org.yaml: {key} is never read"


def test_stack_and_gates_keys_are_read(pack: Path):
    assert top_keys((pack / "stack.yaml").read_text()) == ["commands"]
    assert top_keys((pack / "gates.yaml").read_text()) == ["deny_rules"]
    (pack / "stack.yaml").write_text('commands:\n  test: "make check"\n')
    (pack / "gates.yaml").write_text('deny_rules:\n  - "Bash(rm *)"\n')
    allow, deny = build_allowlist(pack)
    assert "Bash(make check *)" in allow
    assert "Bash(rm *)" in deny


def test_scaffolded_deny_rules_reach_the_allowlist(pack: Path):
    _, deny = build_allowlist(pack)
    assert "Bash(gh auth switch *)" in deny
