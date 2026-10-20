"""Check the public source selection without printing file contents or secrets."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("wechat-compose-article", "wechat-distill-style", "wechat-manage-style-library")


def check() -> dict:
    files = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    files = sorted({x for x in files if x})
    errors = []
    forbidden = ("build/", "dist/", "outputs/", "work/", "tests/golden/", ".local/", ".venv/")
    brands = re.compile(r"khazix|qbit|卡兹克|量子位", re.I)
    secret = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9_-]{35,}")
    absolute = re.compile(r"[A-Z]:[\\/](?:Users[\\/]|official account develop[\\/]|Phd Research[\\/])", re.I)
    for name in files:
        p = ROOT / name
        if name.startswith(forbidden) or p.name == "runtime.json" or p.suffix in (".exe", ".zip", ".pyc"):
            errors.append({"path": name, "reason": "non-public or generated file"})
        if name.startswith("resources/builtin-styles/") and not name.startswith("resources/builtin-styles/basic-editorial-v1.0.0/"):
            errors.append({"path": name, "reason": "unexpected style pack"})
        if not p.is_file() or p.suffix not in (".md", ".py", ".yaml", ".yml", ".toml", ".json", ".html", ".cmd", ".txt"):
            continue
        text = p.read_text(encoding="utf-8")
        # The scanner contains its own forbidden-marker definitions.
        if p.resolve() != Path(__file__).resolve():
            for pattern, reason in ((brands, "reference-account marker"), (secret, "credential-shaped content"), (absolute, "personal source path")):
                if pattern.search(text):
                    errors.append({"path": name, "reason": reason})
        if p.suffix == ".md":
            for target in re.findall(r"\]\(([^\s)]+)\)", text):
                if target.startswith(("https://", "http://", "#", "mailto:")):
                    continue
                if not (p.parent / target.split("#")[0]).exists():
                    errors.append({"path": name, "reason": "missing linked resource: " + target})
    for skill in SKILLS:
        path = ROOT / "plugins/wechat-content-studio/skills" / skill
        if (path / "scripts/run_cli.py").read_bytes() != (ROOT / "tools/skill_runner.py").read_bytes():
            errors.append({"path": skill, "reason": "runner drift"})
    return {"status": "failed" if errors else "passed", "files_checked": len(files), "errors": errors,
            "scope": "Public source inventory, known excluded assets, links and credential patterns"}


if __name__ == "__main__":
    result = check()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(bool(result["errors"]))
