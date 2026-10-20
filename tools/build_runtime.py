"""Build and smoke-test the self-contained Windows CLI runtime."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPOSITORY / "build" / "runtime"
DEFAULT_WORK = REPOSITORY / "build" / "pyinstaller"
SPEC = REPOSITORY / "tools" / "pyinstaller" / "wechat-studio.spec"


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _controlled_directory(path: Path, allowed_root: Path) -> Path:
    resolved = path.resolve()
    if resolved == allowed_root.resolve() or not _inside(resolved, allowed_root):
        raise ValueError(f"Refusing uncontrolled build directory: {resolved}")
    return resolved


def _run(command: list[str], *, cwd: Path = REPOSITORY) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def build_runtime(output_root: Path, work_root: Path) -> Path:
    try:
        import PyInstaller  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "PyInstaller is required. Install it in the build environment first."
        ) from exc

    output_root = _controlled_directory(output_root, REPOSITORY / "build")
    work_root = _controlled_directory(work_root, REPOSITORY / "build")
    for directory in (output_root, work_root):
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(output_root),
        "--workpath",
        str(work_root),
        str(SPEC),
    ]
    completed = _run(command)
    if completed.returncode != 0:
        raise RuntimeError(
            "PyInstaller failed.\n" + completed.stdout + "\n" + completed.stderr
        )

    runtime = output_root / "wechat-studio"
    executable = runtime / "wechat-studio.exe"
    if not executable.is_file():
        raise RuntimeError(f"Runtime executable was not created: {executable}")
    smoke_test_runtime(executable)
    return runtime


def smoke_test_runtime(executable: Path) -> None:
    version = _run([str(executable), "--version"], cwd=executable.parent)
    if version.returncode != 0 or "wechat-studio 0.1.1" not in version.stdout:
        raise RuntimeError(
            "Frozen runtime version smoke test failed.\n"
            + version.stdout
            + "\n"
            + version.stderr
        )
    with tempfile.TemporaryDirectory(prefix="wcs-runtime-smoke-") as temporary:
        root = Path(temporary)
        initialized = _run(
            [
                str(executable),
                "--format",
                "json",
                "--workspace",
                str(root / "workspace"),
                "--state-root",
                str(root / "state"),
                "workspace",
                "init",
            ],
            cwd=root,
        )
        if initialized.returncode != 0:
            raise RuntimeError(
                "Frozen runtime workspace smoke test failed.\n"
                + initialized.stdout
                + "\n"
                + initialized.stderr
            )
        document = json.loads(initialized.stdout)
        if document.get("ok") is not True:
            raise RuntimeError("Frozen runtime returned an unsuccessful JSON result.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--work", type=Path, default=DEFAULT_WORK)
    args = parser.parse_args()
    runtime = build_runtime(args.output, args.work)
    print(json.dumps({"runtime": str(runtime)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
