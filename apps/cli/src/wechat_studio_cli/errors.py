"""CLI-only stable errors and exit-code mapping."""

from __future__ import annotations

from typing import Any, Mapping

from wechat_studio.errors import WeChatStudioError


class CliUsageError(WeChatStudioError):
    default_code = "WCS-CLI-001"


class CliInternalError(WeChatStudioError):
    default_code = "WCS-CLI-002"


def usage_error(message: str, **context: Any) -> CliUsageError:
    return CliUsageError(message, context=context)


def exit_code_for_error(error: WeChatStudioError) -> int:
    prefix = error.code.split("-", 2)[1] if error.code.count("-") >= 2 else "CLI"
    return {
        "CLI": 2,
        "CONTRACT": 20,
        "PATH": 21,
        "STORAGE": 22,
        "PROJECT": 30,
        "MATERIAL": 31,
        "ANCHOR": 32,
        "RENDER": 40,
        "STYLE": 50,
        "PRESET": 51,
        "SAMPLE": 60,
        "DISTILL": 61,
        "MIGRATE": 70,
    }.get(prefix, 99)
