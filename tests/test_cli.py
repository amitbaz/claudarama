import subprocess
import sys
from pathlib import Path


def run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Helper to run claudarama CLI via python -m."""
    return subprocess.run(
        [sys.executable, "-m", "claudarama", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def assert_help_output(output: str) -> None:
    """Verify standard help text components."""
    assert "usage:" in output.lower() or "claudarama" in output
    assert "init" in output


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


def test_init_creates_pack(tmp_path: Path):
    """Running claudarama init creates a .claudarama/ pack with required files."""
    result = run_cli("init", cwd=tmp_path)
    assert result.returncode == 0

    pack_dir = tmp_path / ".claudarama"
    assert pack_dir.is_dir()

    expected_files = [
        "company.md",
        "org.yaml",
        "gates.yaml",
        "stack.yaml",
    ]
    for filename in expected_files:
        target_file = pack_dir / filename
        assert target_file.is_file(), f"Expected {filename} to exist in {pack_dir}"
        assert target_file.stat().st_size > 0, f"Expected {filename} to not be empty"

    expected_dirs = [
        "profiles",
        "scenarios",
        "plugins",
        "company/okrs",
        "company/all-hands",
        "company/retros",
        "company/reviews",
    ]
    for dirname in expected_dirs:
        target_subdir = pack_dir / dirname
        assert target_subdir.is_dir(), f"Expected directory {dirname} to exist in {pack_dir}"


def test_init_directory_already_exists(tmp_path: Path):
    """Running claudarama init exits cleanly when .claudarama directory already exists."""
    pack_dir = tmp_path / ".claudarama"
    pack_dir.mkdir()
    sentinel_file = pack_dir / "custom.txt"
    sentinel_file.write_text("user content")

    result = run_cli("init", cwd=tmp_path)
    assert result.returncode == 0
    assert "already exists" in (result.stdout + result.stderr).lower()
    # Ensure existing content wasn't destroyed
    assert sentinel_file.read_text() == "user content"
