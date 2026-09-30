import argparse
import sys
from typing import Sequence

from claudarama.scaffold import init_pack


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

    # init subcommand
    subparsers.add_parser(
        "init",
        help="Initialize a default .claudarama pack in the current directory",
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

    # up subcommand
    up_parser = subparsers.add_parser(
        "up",
        help="Start the FastMCP daemon and initialize office.db",
    )
    up_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind the daemon (default: 127.0.0.1)",
    )
    up_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the daemon (default: 8000)",
    )

    # open subcommand
    open_parser = subparsers.add_parser(
        "open",
        help="Connect an interactive Claude session to the daemon's MCP endpoint",
    )
    open_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Daemon host (default: 127.0.0.1)",
    )
    open_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Daemon port (default: 8000)",
    )

    # talk subcommand
    talk_parser = subparsers.add_parser(
        "talk",
        help="Open an interactive session with a named person",
    )
    talk_parser.add_argument("name", help="Name of the person to talk to")
    talk_parser.add_argument("--host", default="127.0.0.1", help="Daemon host (default: 127.0.0.1)")
    talk_parser.add_argument("--port", type=int, default=8000, help="Daemon port (default: 8000)")

    # status subcommand
    status_parser = subparsers.add_parser(
        "status",
        help="Show usage totals per person, ticket and ritual",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "init":
        success, message = init_pack()
        print(message)
        return 0 if success else 1

    if args.command == "up":
        from claudarama.daemon import run_daemon

        run_daemon(host=args.host, port=args.port)
        return 0

    if args.command == "open":
        from claudarama.session import open_ceo_session

        return open_ceo_session(host=args.host, port=args.port)

    if args.command == "talk":
        from claudarama.session import talk_to_person

        return talk_to_person(args.name, host=args.host, port=args.port)

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
