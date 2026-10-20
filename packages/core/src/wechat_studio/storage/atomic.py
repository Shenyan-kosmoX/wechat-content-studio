"""Validated same-directory atomic file replacement."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from wechat_studio.errors import AtomicWriteError


PathValidator = Callable[[Path], None]
CommitCallback = Callable[[], None]


def atomic_write_bytes(
    destination: str | Path,
    data: bytes,
    *,
    validator: PathValidator | None = None,
) -> Path:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if validator is not None:
            validator(temporary)
        os.replace(temporary, target)
        temporary = None
        return target
    except Exception as exc:
        raise AtomicWriteError(
            f"Atomic write failed for {target}.",
            context={"path": str(target), "reason": str(exc)},
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def atomic_write_text(
    destination: str | Path,
    text: str,
    *,
    encoding: str = "utf-8",
    validator: PathValidator | None = None,
) -> Path:
    return atomic_write_bytes(destination, text.encode(encoding), validator=validator)


def atomic_replace_directory(
    destination: str | Path,
    staged_directory: str | Path,
    *,
    after_replace: CommitCallback | None = None,
) -> Path:
    """Replace one directory and restore the old version if commit work fails."""

    target = Path(destination).resolve()
    staged = Path(staged_directory).resolve()
    if not staged.is_dir():
        raise AtomicWriteError(
            f"Staged directory does not exist: {staged}",
            context={"destination": str(target), "staged": str(staged)},
        )
    if staged.parent != target.parent:
        raise AtomicWriteError(
            "Atomic directory replacement requires a same-directory staging folder.",
            context={"destination": str(target), "staged": str(staged)},
        )

    backup = target.parent / f".{target.name}.backup"
    if backup.exists():
        raise AtomicWriteError(
            f"Stale build backup blocks replacement: {backup}",
            context={"destination": str(target), "backup": str(backup)},
        )

    had_target = target.exists()
    try:
        if had_target:
            os.replace(target, backup)
        os.replace(staged, target)
        if after_replace is not None:
            after_replace()
    except Exception as exc:
        try:
            if target.exists():
                shutil.rmtree(target)
            if had_target and backup.exists():
                os.replace(backup, target)
        except Exception as restore_exc:
            raise AtomicWriteError(
                f"Directory replacement and rollback both failed for {target}.",
                context={
                    "destination": str(target),
                    "reason": str(exc),
                    "rollback_reason": str(restore_exc),
                    "backup": str(backup),
                },
            ) from restore_exc
        raise AtomicWriteError(
            f"Directory replacement failed for {target}; previous contents were restored.",
            context={"destination": str(target), "reason": str(exc)},
        ) from exc
    finally:
        if staged.exists():
            shutil.rmtree(staged, ignore_errors=True)

    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)
    return target
