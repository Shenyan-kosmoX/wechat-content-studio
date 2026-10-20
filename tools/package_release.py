"""Create and verify the versioned Windows x64 release archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path

from validate_distribution import validate_distribution


REPOSITORY = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPOSITORY / "dist" / "local-marketplace"
RELEASE_NAME = "wechat-content-studio-0.1.1-windows-x64"
DEFAULT_ARCHIVE = REPOSITORY / "dist" / f"{RELEASE_NAME}.zip"


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _controlled_archive(path: Path) -> Path:
    resolved = path.resolve()
    dist_root = (REPOSITORY / "dist").resolve()
    if not _inside(resolved, dist_root) or resolved.suffix.lower() != ".zip":
        raise ValueError(f"Refusing uncontrolled release archive: {resolved}")
    return resolved


def _write_archive(source: Path, archive: Path) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{archive.stem}.", suffix=".zip.tmp", dir=archive.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as bundle:
            for path in sorted(item for item in source.rglob("*") if item.is_file()):
                relative = path.relative_to(source)
                bundle.write(path, (Path(RELEASE_NAME) / relative).as_posix())
        with zipfile.ZipFile(temporary, "r") as bundle:
            bad = bundle.testzip()
            if bad is not None:
                raise ValueError(f"Release archive CRC check failed for {bad}.")
        os.replace(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)


def _verify_extracted_archive(archive: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="wcs-release-verify-") as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(archive, "r") as bundle:
            bundle.extractall(root)
        validate_distribution(root / RELEASE_NAME)


def package_release(source: Path, archive: Path) -> dict[str, object]:
    source = source.resolve()
    archive = _controlled_archive(archive)
    validate_distribution(source)
    _write_archive(source, archive)
    _verify_extracted_archive(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    return {
        "archive": str(archive),
        "sha256": digest,
        "checksum_file": str(checksum),
        "bytes": archive.stat().st_size,
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    args = parser.parse_args()
    result = package_release(args.source, args.archive)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
