"""Schema-validated stdout/stderr documents for CLI consumers."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TextIO

from wechat_studio.contracts import ContractValidator
from wechat_studio.errors import WeChatStudioError


@dataclass(frozen=True, slots=True)
class CommandExecution:
    command: str
    data: Mapping[str, Any]
    warnings: Sequence[Mapping[str, Any]] = ()
    after_emit: Callable[[], None] | None = None


def _success_document(execution: CommandExecution) -> dict[str, Any]:
    return {
        "cli_result_schema_version": "1.0",
        "ok": True,
        "command": execution.command,
        "data": dict(execution.data),
        "warnings": [dict(item) for item in execution.warnings],
    }


def _error_document(command: str, error: WeChatStudioError) -> dict[str, Any]:
    return {
        "cli_result_schema_version": "1.0",
        "ok": False,
        "command": command,
        "error": error.to_dict(),
    }


def _write(document: Mapping[str, Any], output_format: str, stream: TextIO) -> None:
    ContractValidator().validate_or_raise(document, "cli-result")
    if output_format == "json":
        stream.write(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    elif document["ok"]:
        data = document["data"]
        stream.write(f"OK {document['command']}\n")
        stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        for warning in document.get("warnings", []):
            stream.write(f"WARNING {warning['code']}: {warning['message']}\n")
    else:
        error = document["error"]
        stream.write(f"ERROR {error['code']}: {error['message']}\n")
        if error["context"]:
            stream.write(json.dumps(error["context"], ensure_ascii=False, indent=2) + "\n")
    stream.flush()


def emit_success(
    execution: CommandExecution,
    *,
    output_format: str,
    stream: TextIO,
) -> None:
    _write(_success_document(execution), output_format, stream)


def emit_error(
    command: str,
    error: WeChatStudioError,
    *,
    output_format: str,
    stream: TextIO,
) -> None:
    _write(_error_document(command, error), output_format, stream)
