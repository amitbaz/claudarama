#!/usr/bin/env python3
"""Script to verify scenario constraints have not been loosened compared to base branch."""

import sys
from pathlib import Path

# Add src directory to sys.path so scripts/check_sealing.py works without prior pip install
repo_root = Path(__file__).resolve().parent.parent
src_dir = repo_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from claudarama.scenario.sealing import run_sealing_cli

if __name__ == "__main__":
    sys.exit(run_sealing_cli())
