"""Argument parser and command registration."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from . import CLI_VERSION, CORE_VERSION
from .commands import article, preview, project, sample, style, workspace
from .errors import CliUsageError


class StableArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliUsageError(
            message,
            context={"usage": self.format_usage().strip(), "program": self.prog},
        )


def requested_format(argv: Sequence[str]) -> str:
    for index, value in enumerate(argv):
        if value == "--format" and index + 1 < len(argv):
            return argv[index + 1] if argv[index + 1] in {"json", "text"} else "text"
        if value.startswith("--format="):
            candidate = value.split("=", 1)[1]
            return candidate if candidate in {"json", "text"} else "text"
    return "text"


def build_parser() -> StableArgumentParser:
    parser = StableArgumentParser(prog="wechat-studio")
    parser.add_argument(
        "--version",
        action="version",
        version=f"wechat-studio {CLI_VERSION} (core {CORE_VERSION})",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--workspace", help="Override the user data root.")
    parser.add_argument("--state-root", help="Override cache/log/lock state root.")
    parser.add_argument("--resources-root", help="Override bundled resources for development/tests.")
    top = parser.add_subparsers(dest="domain", required=True)
    for module in (workspace, article, preview, sample, style, project):
        module.configure(top)
    return parser
