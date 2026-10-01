import os
import subprocess
import sys
from pathlib import Path


def run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Helper to run claudarama CLI via python -m."""
    repo_root = Path(__file__).resolve().parent.parent
    src_dir = str(repo_root / "src")
    env = dict(os.environ)
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{src_dir}:{existing_pp}" if existing_pp else src_dir

    return subprocess.run(
        [sys.executable, "-m", "claudarama", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )


def assert_help_output(output: str) -> None:
    """Verify standard help text components."""
    assert "usage:" in output.lower() or "claudarama" in output
    assert "setup" in output
    assert "open" in output


def test_cli_no_args():
    """Verify that invoking claudarama with no arguments prints help and exits 0."""
    result = run_cli()
    assert result.returncode == 0
    assert_help_output(result.stdout)


def test_cli_help():
    """Verify that claudarama CLI provides a basic help menu."""
    result = run_cli("--help")
    assert result.returncode == 0
    assert_help_output(result.stdout)


def test_bin_claudarama_executable():
    """Verify that bin/claudarama script executes cleanly and provides help."""
    repo_root = Path(__file__).resolve().parent.parent
    bin_script = repo_root / "bin" / "claudarama"
    assert bin_script.exists()

    result = subprocess.run(
        [str(bin_script), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert_help_output(result.stdout)


def test_cli_eval_help():
    """Verify that claudarama eval provides help text with --runs and --against."""
    result = run_cli("eval", "--help")
    assert result.returncode == 0
    output = result.stdout.lower()
    assert "--runs" in output
    assert "--against" in output


def test_cli_eval_passes_scenario(tmp_path: Path):
    scenario = tmp_path / "valid.json"
    scenario.write_text('{"name": "cli-test", "role": "eng", "prompt": "build", "checks": {"includes": ["DONE"]}}')

    result = run_cli("eval", str(scenario), "--mock-response", "Status: DONE", cwd=tmp_path)
    assert result.returncode == 0
    assert "[PASS]" in result.stdout
    assert "cli-test" in result.stdout


def test_cli_eval_fails_scenario(tmp_path: Path):
    scenario = tmp_path / "valid.json"
    scenario.write_text('{"name": "cli-fail", "role": "eng", "prompt": "build", "checks": {"includes": ["DONE"]}}')

    result = run_cli("eval", str(scenario), "--mock-response", "Status: FAILED", cwd=tmp_path)
    assert result.returncode == 1
    assert "[FAIL]" in result.stdout
    assert "cli-fail" in result.stdout


def test_cli_eval_runs_majority(tmp_path: Path):
    scenario = tmp_path / "scenario.json"
    scenario.write_text('{"name": "cli-runs", "role": "eng", "prompt": "build", "checks": {"includes": ["DONE"]}}')

    result = run_cli("eval", str(scenario), "--runs", "3", "--mock-response", "Status: DONE", cwd=tmp_path)
    assert result.returncode == 0
    assert "3/3 runs passed" in result.stdout


def test_cli_eval_against_git_ref(tmp_path: Path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=tmp_path, check=True)

    scenario = tmp_path / "scenario.json"
    scenario.write_text('{"name": "cli-against", "role": "eng", "prompt": "build", "checks": {"includes": ["OLD"]}}')
    subprocess.run(["git", "add", "scenario.json"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=tmp_path, check=True)
    base_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()

    scenario.write_text('{"name": "cli-against", "role": "eng", "prompt": "build", "checks": {"includes": ["NEW"]}}')

    result = run_cli("eval", str(scenario), "--against", base_commit, "--mock-response", "Value: NEW", cwd=tmp_path)
    assert result.returncode == 0
    assert "IMPROVED" in result.stdout


def test_cli_eval_default_discovery(tmp_path: Path):
    scenarios_dir = tmp_path / ".claudarama" / "scenarios"
    scenarios_dir.mkdir(parents=True)
    scenario_file = scenarios_dir / "discovered.json"
    scenario_file.write_text('{"name": "discovered-test", "role": "eng", "prompt": "build", "checks": {"includes": ["FOUND"]}}')

    result = run_cli("eval", "--mock-response", "Output: FOUND", cwd=tmp_path)
    assert result.returncode == 0
    assert "[PASS]" in result.stdout
    assert "discovered-test" in result.stdout


def test_cli_eval_against_invalid_git_ref(tmp_path: Path):
    scenario = tmp_path / "scenario.json"
    scenario.write_text('{"name": "cli-against-err", "role": "eng", "prompt": "build", "checks": {"includes": ["TEST"]}}')

    result = run_cli("eval", str(scenario), "--against", "nonexistent-branch-or-tag", cwd=tmp_path)
    assert result.returncode == 1
    assert "Invalid git reference" in result.stderr


def test_cli_eval_invalid_runs_zero(tmp_path: Path):
    scenario = tmp_path / "scenario.json"
    scenario.write_text('{"name": "cli-runs-err", "role": "eng", "prompt": "build", "checks": {"includes": ["TEST"]}}')

    result = run_cli("eval", str(scenario), "--runs", "0", cwd=tmp_path)
    assert result.returncode == 1
    assert "--runs must be at least 1" in result.stderr


def test_cli_eval_scenario_with_judge(tmp_path: Path):
    scenario = tmp_path / "judge_scenario.json"
    scenario.write_text(
        '{"name": "judge-test", "role": "eng", "prompt": "build", "judge": "Is it good?", "checks": {"includes": ["DONE"]}}'
    )

    result = run_cli("eval", str(scenario), "--mock-response", "Status: DONE", cwd=tmp_path)
    assert result.returncode == 0
    assert "[PASS]" in result.stdout


def test_cli_up_and_talk_are_gone():
    """There is no server to start and no direct talk with a Role (ADR-0003)."""
    for removed in (["up"], ["talk", "Bender"]):
        result = run_cli(*removed)
        assert result.returncode == 2
        assert "invalid choice" in result.stderr


def test_cli_open_invokes_claude_session():
    from unittest.mock import patch
    import claudarama.cli as cli

    with patch("claudarama.session.open_ceo_session", return_value=0) as mock_open:
        assert cli.main(["open"]) == 0
        mock_open.assert_called_once_with(attach=False)

