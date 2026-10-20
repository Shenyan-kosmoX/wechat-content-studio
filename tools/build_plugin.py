"""Assemble the source plugin and frozen runtime into a local marketplace."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
SOURCE_PLUGIN = REPOSITORY / "plugins" / "wechat-content-studio"
DEFAULT_RUNTIME = REPOSITORY / "build" / "runtime" / "wechat-studio"
DEFAULT_OUTPUT = REPOSITORY / "dist" / "local-marketplace"


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _validate_output(path: Path) -> Path:
    resolved = path.resolve()
    dist_root = (REPOSITORY / "dist").resolve()
    if resolved == dist_root or not _inside(resolved, dist_root):
        raise ValueError(f"Refusing uncontrolled distribution directory: {resolved}")
    return resolved


def build_plugin(runtime: Path, output: Path) -> Path:
    runtime = runtime.resolve()
    if not (runtime / "wechat-studio.exe").is_file():
        raise FileNotFoundError(f"Frozen runtime is missing: {runtime}")
    output = _validate_output(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging: Path | None = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    )
    backup = output.parent / f".{output.name}.backup"
    if backup.exists():
        raise FileExistsError(f"Stale distribution backup blocks the build: {backup}")
    had_output = output.exists()
    try:
        assert staging is not None
        plugin_destination = staging / "plugins" / "wechat-content-studio"
        shutil.copytree(SOURCE_PLUGIN, plugin_destination)
        tools_destination = staging / "tools"
        tools_destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            REPOSITORY / "tools" / "style_bundle.py",
            tools_destination / "style_bundle.py",
        )
        runtime_destination = (
            plugin_destination / "scripts" / "runtime" / "windows-x64"
        )
        shutil.copytree(runtime, runtime_destination)

        marketplace = {
            "name": "wechat-content-studio-local",
            "interface": {"displayName": "WeChat Content Studio Local"},
            "plugins": [
                {
                    "name": "wechat-content-studio",
                    "source": {
                        "source": "local",
                        "path": "./plugins/wechat-content-studio",
                    },
                    "policy": {
                        "installation": "AVAILABLE",
                        "authentication": "ON_INSTALL",
                    },
                    "category": "Productivity",
                }
            ],
        }
        marketplace_path = staging / ".agents" / "plugins" / "marketplace.json"
        marketplace_path.parent.mkdir(parents=True, exist_ok=True)
        marketplace_path.write_text(
            json.dumps(marketplace, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        release_manifest = {
            "release_manifest_schema_version": "1.0",
            "plugin": {"name": "wechat-content-studio", "version": "0.1.1"},
            "core_version": "0.1.1",
            "cli_version": "0.1.1",
            "data_schema_version": "1.0",
            "platform": "windows-x64",
            "runtime": "plugins/wechat-content-studio/scripts/runtime/windows-x64/wechat-studio.exe",
            "marketplace": ".agents/plugins/marketplace.json",
            "skills": [
                "wechat-compose-article",
                "wechat-distill-style",
                "wechat-manage-style-library",
            ],
            "delivery": {
                "browser_preview": True,
                "clipboard_mime_types": ["text/html", "text/plain"],
                "image_copy_primary": True,
                "manual_image_fallback": True,
            },
            "boundaries": {
                "controls_wechat_backend": False,
                "publishes_automatically": False,
                "screenshot_required": False,
                "wechat_validation_by_user": True,
            },
        }
        (staging / "release-manifest.json").write_text(
            json.dumps(release_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (staging / "INSTALL.md").write_text(
            "# WeChat Content Studio 0.1.1\n\n"
            "This package contains a self-contained Windows x64 runtime. Python is not required.\n\n"
            "## Install in Codex\n\n"
            "1. Extract the entire release folder.\n"
            "2. Run `codex plugin marketplace add <extracted-release-folder>`.\n"
            "3. Run `codex plugin add wechat-content-studio@wechat-content-studio-local`.\n"
            "4. Start a new Codex task so the three skills are discovered.\n\n"
            "## Delivery boundary\n\n"
            "The plugin creates a browser preview and copies both `text/html` and `text/plain`. "
            "Paste into the WeChat Official Account editor and report the result in text. "
            "No screenshot is required. The plugin does not log in, save drafts, or publish.\n",
            encoding="utf-8",
        )
        (staging / "ACCEPTANCE.md").write_text(
            "# Release validation\n\n"
            "Release: `wechat-content-studio 0.1.1` for Windows x64\n\n"
            "This file describes checks to run. Building a package does not record them as passed.\n\n"
            "Run `python -m pytest` for the source tests, then run "
            "`python tools/validate_distribution.py` to validate this package and exercise "
            "the runtime from a temporary installation directory. Save their output "
            "with the release record.\n\n"
            "After installation, check that Codex discovers the three skills. Open an "
            "article preview, copy its rich text, and paste it into the WeChat editor "
            "to check the appearance and images before publishing.\n",
            encoding="utf-8",
        )

        if had_output:
            os.replace(output, backup)
        try:
            os.replace(staging, output)
            staging = None
        except Exception:
            if had_output and backup.exists():
                os.replace(backup, output)
            raise
        if backup.exists():
            shutil.rmtree(backup)
        return output
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = build_plugin(args.runtime, args.output)
    print(json.dumps({"marketplace": str(output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
