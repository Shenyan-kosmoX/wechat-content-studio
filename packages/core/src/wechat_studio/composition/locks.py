"""Small cross-platform lock files for project-level mutations."""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from wechat_studio.errors import LockBusyError


@contextmanager
def exclusive_lock(
    path: str | Path,
    *,
    timeout_seconds: float = 0.0,
    poll_seconds: float = 0.05,
) -> Iterator[Path]:
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + max(timeout_seconds, 0.0)
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise LockBusyError(
                    f"Resource is already locked: {lock_path}",
                    context={"path": str(lock_path)},
                ) from exc
            time.sleep(max(0.01, min(poll_seconds, 0.25)))

    try:
        payload = json.dumps(
            {"pid": os.getpid(), "created_at_epoch": time.time()},
            ensure_ascii=False,
        ).encode("utf-8")
        os.write(descriptor, payload)
        os.close(descriptor)
        descriptor = None
        yield lock_path
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass
