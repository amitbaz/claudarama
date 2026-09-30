"""CLI entrypoint for running python -m claudarama.scenario."""

import sys
from claudarama.scenario.cli import run_checker_cli

if __name__ == "__main__":
    sys.exit(run_checker_cli())
