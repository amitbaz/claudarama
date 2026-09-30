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

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
