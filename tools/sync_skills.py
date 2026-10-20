"""Maintain the same portable runtime entry in all three skills."""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for skill in (ROOT / "plugins/wechat-content-studio/skills").iterdir():
    if (skill / "SKILL.md").is_file():
        destination = skill / "scripts/run_cli.py"
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(ROOT / "tools/skill_runner.py", destination)
        print(destination.relative_to(ROOT))
