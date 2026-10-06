import argparse
import sys

from atlas_cli import __version__
from atlas_cli.commands import doctor, init, link, plugin, status


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atlas",
        description="Create and keep Atlases in order — https://atlas.paranoid.software",
    )
    parser.add_argument("--version", action="version", version=f"atlas {__version__}")
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    init.register(subparsers)
    link.register(subparsers)
    doctor.register(subparsers)
    plugin.register(subparsers)
    status.register(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
