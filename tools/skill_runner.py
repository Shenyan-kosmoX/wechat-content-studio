"""Source for the identical runner shipped with each skill. See sync_skills.py."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    skill = Path(__file__).resolve().parents[1]
    config = skill / "runtime.json"
    if config.is_file():
        # Generated locally by install_skills.py, never included in the public source.
        interpreter = json.loads(config.read_text(encoding="utf-8"))["python"]
        return subprocess.call([interpreter, "-m", "wechat_studio_cli", *sys.argv[1:]], shell=False)
    launcher = skill.parent.parent / "scripts/runtime/windows-x64/wechat-studio.exe"
    if launcher.is_file():
        return subprocess.call([str(launcher), *sys.argv[1:]], shell=False)
    interpreter = os.environ.get("WECHAT_STUDIO_PYTHON", sys.executable)
    return subprocess.call([interpreter, "-m", "wechat_studio_cli", *sys.argv[1:]], shell=False)


if __name__ == "__main__":
    raise SystemExit(main())
