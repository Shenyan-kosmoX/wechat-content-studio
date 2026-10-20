"""Run the public source example and installed skill launchers in a fresh workspace."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(argv: list[str], cwd: Path) -> str:
    p = subprocess.run([sys.executable, *argv], cwd=cwd, capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if p.returncode:
        raise RuntimeError(f"Command failed: {argv}\n{p.stdout}\n{p.stderr}")
    return p.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    cli = ["-m", "wechat_studio_cli", "--format", "json", "--workspace", str(output / "workspace"), "--state-root", str(output / "state")]
    project_id = "public-smoke"
    if (output / "workspace/articles" / project_id).exists():
        raise RuntimeError("Choose a fresh output directory; previous outputs are preserved.")
    steps = [
        ["workspace", "init"],
        ["article", "create", "--name", "Public example", "--mode", "layout_only", "--project-id", project_id, "--article-file", str(ROOT / "examples/first-article.md")],
        ["article", "validate", project_id],
        ["article", "render", project_id],
    ]
    records = []
    for step in steps:
        response = json.loads(run([*cli, *step], output))
        if response.get("ok") is not True:
            raise RuntimeError("CLI returned unsuccessful result")
        records.append({"step": " ".join(step[:2]), "ok": True})
    build = output / "workspace/articles" / project_id / "build"
    preview = (build / "wechat_preview.html").read_text(encoding="utf-8")
    for expected in ('id="copy-rich-text"', '"text/html"', '"text/plain"', 'id="copy-with-placeholders"'):
        if expected not in preview:
            raise RuntimeError(f"Preview is missing {expected}")
    with tempfile.TemporaryDirectory(prefix="wcs-skill-smoke-") as temp:
        target = Path(temp) / "skills"
        installed = json.loads(run([str(ROOT / "tools/install_skills.py"), "--target", str(target)], Path(temp)))
        for skill_path in installed["installed"]:
            version = run([str(Path(skill_path) / "scripts/run_cli.py"), "--version"], Path(temp))
            if "0.1.1" not in version:
                raise RuntimeError("Installed skill resolved the wrong runtime")
        again = subprocess.run([sys.executable, str(ROOT / "tools/install_skills.py"), "--target", str(target)], capture_output=True, text=True)
        if again.returncode == 0:
            raise RuntimeError("Installer overwrote an existing skill")
    report = {"status": "passed", "steps": records, "skill_launchers": 3,
              "clipboard_markup": "present", "wechat_editor_paste": "manual user check",
              "preview": str(build / "wechat_preview.html")}
    (output / "smoke-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
