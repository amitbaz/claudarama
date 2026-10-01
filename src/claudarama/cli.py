import argparse
import sys
from typing import Sequence

from claudarama.scaffold import setup_pack


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="claudarama",
        description="Claudarama: AI startup plugin for software projects",
    )
    subparsers = parser.add_subparsers(
        title="subcommands",
        dest="command",
        help="Available commands",
    )

    # setup subcommand
    subparsers.add_parser(
        "setup",
        help="Scaffold a default .claudarama pack in the current directory",
    )

    # eval subcommand
    eval_parser = subparsers.add_parser(
        "eval",
        help="Run scenario evaluations against mock LLM or stub",
    )
    eval_parser.add_argument(
        "paths",
        nargs="*",
        help="Path(s) to scenario JSON files or directories containing scenarios",
    )
    eval_parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of evaluation runs per scenario (requires majority to pass)",
    )
    eval_parser.add_argument(
        "--against",
        type=str,
        default=None,
        help="Git reference (branch, tag, or commit) to compare execution against",
    )
    eval_parser.add_argument(
        "--mock-response",
        type=str,
        default=None,
        help="Mock response text for offline execution/testing",
    )

    # open subcommand
    open_parser = subparsers.add_parser(
        "open",
        help="Open the office: start the CEO's Session with the office server attached",
    )
    open_parser.add_argument(
        "--attach",
        action="store_true",
        help="Open in the Claude Code session this runs in instead of starting one (what /claudarama:open runs)",
    )

    # watch subcommand
    subparsers.add_parser(
        "watch",
        help="Wait until a gate opens, say which, and end (the Assistant runs this in the background of the Session)",
    )

    # status subcommand
    status_parser = subparsers.add_parser(
        "status",
        help="Show usage totals per person, ticket and ritual, and a report for each mandate: "
             "each Role's turns, every NO and FAIL with its reason, every question, and each transcript",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "setup":
        success, message = setup_pack()
        print(message, file=sys.stdout if success else sys.stderr)
        return 0 if success else 1

    if args.command == "open":
        from claudarama.session import open_ceo_session

        return open_ceo_session(attach=args.attach)

    if args.command == "watch":
        from claudarama.db import get_office_db_path
        from claudarama.session import watch_gates

        print(next(watch_gates(get_office_db_path())), flush=True)
        return 0

    if args.command == "eval":
        from claudarama.scenario.cli import run_eval_cli

        return run_eval_cli(
            paths=args.paths,
            runs=args.runs,
            against=args.against,
            mock_response=args.mock_response,
        )

    if args.command == "status":
        from claudarama.status import print_status
        return print_status()

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
