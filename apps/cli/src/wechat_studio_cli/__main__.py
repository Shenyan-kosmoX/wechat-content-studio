"""Stable command-line entry point for WeChat Content Studio."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from wechat_studio.errors import WeChatStudioError

from .errors import CliInternalError, CliUsageError, exit_code_for_error
from .output import CommandExecution, emit_error, emit_success
from .parser import build_parser, requested_format


def _configure_utf8_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="strict")


def main(argv: Sequence[str] | None = None) -> int:
    _configure_utf8_streams()
    arguments = list(sys.argv[1:] if argv is None else argv)
    output_format = requested_format(arguments)
    command = "cli.parse"
    try:
        parsed = build_parser().parse_args(arguments)
        output_format = parsed.format
        command = parsed.command_name
        execution = parsed.handler(parsed)
        if not isinstance(execution, CommandExecution):
            raise CliInternalError(
                "CLI command returned an invalid execution result.",
                context={"command": command},
            )
        emit_success(execution, output_format=output_format, stream=sys.stdout)
        if execution.after_emit is not None:
            execution.after_emit()
        return 0
    except KeyboardInterrupt:
        return 130
    except (CliUsageError, WeChatStudioError) as exc:
        emit_error(command, exc, output_format=output_format, stream=sys.stderr)
        return exit_code_for_error(exc)
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        wrapped = CliInternalError(
            "Unexpected CLI failure.",
            context={"command": command, "exception_type": type(exc).__name__},
        )
        emit_error(command, wrapped, output_format=output_format, stream=sys.stderr)
        return exit_code_for_error(wrapped)


if __name__ == "__main__":
    raise SystemExit(main())
