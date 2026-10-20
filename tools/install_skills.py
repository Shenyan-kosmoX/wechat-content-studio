"""Install three skills into an explicitly chosen directory using this Python."""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("wechat-compose-article", "wechat-distill-style", "wechat-manage-style-library")


def install(target: Path) -> list[Path]:
    if importlib.util.find_spec("wechat_studio_cli") is None:
        raise RuntimeError("Install Core and CLI into this Python before installing skills.")
    target = target.expanduser().resolve()
    destinations = [target / name for name in SKILLS]
    for destination in destinations:
        if destination.exists():
            raise FileExistsError(f"Existing skill preserved: {destination}. Choose an empty target or back up the old version first.")
    target.mkdir(parents=True, exist_ok=True)
    for name, destination in zip(SKILLS, destinations):
        shutil.copytree(ROOT / "plugins/wechat-content-studio/skills" / name, destination,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "runtime.json"))
        (destination / "runtime.json").write_text(json.dumps({"python": sys.executable}, indent=2) + "\n", encoding="utf-8")
    return destinations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    try:
        paths = install(args.target)
    except (OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps({"installed": [str(p) for p in paths], "python": sys.executable}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
