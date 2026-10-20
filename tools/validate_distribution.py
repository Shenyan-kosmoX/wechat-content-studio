"""Validate and relocation-smoke-test a built local marketplace."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml


REPOSITORY = Path(__file__).resolve().parents[1]
DEFAULT_DISTRIBUTION = REPOSITORY / "dist" / "local-marketplace"
PLUGIN_NAME = "wechat-content-studio"
FORBIDDEN_DIRECTORY_NAMES = {
    "__pycache__",
    ".pytest_cache",
    "cache",
    "logs",
    "locks",
    "temp",
}
TEXT_SUFFIXES = {
    ".bat",
    ".cmd",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def validate_structure(distribution: Path) -> tuple[Path, Path]:
    marketplace_path = distribution / ".agents" / "plugins" / "marketplace.json"
    release_manifest_path = distribution / "release-manifest.json"
    install_path = distribution / "INSTALL.md"
    acceptance_path = distribution / "ACCEPTANCE.md"
    plugin = distribution / "plugins" / PLUGIN_NAME
    manifest_path = plugin / ".codex-plugin" / "plugin.json"
    executable = plugin / "scripts" / "runtime" / "windows-x64" / "wechat-studio.exe"
    launcher = plugin / "scripts" / "wechat-studio.cmd"
    for required in (
        marketplace_path,
        release_manifest_path,
        install_path,
        acceptance_path,
        manifest_path,
        executable,
        launcher,
    ):
        if not required.is_file():
            raise FileNotFoundError(f"Distribution file is missing: {required}")

    marketplace = _load_json(marketplace_path)
    entries = marketplace.get("plugins")
    if not isinstance(entries, list) or len(entries) != 1:
        raise ValueError("Marketplace must contain exactly one plugin entry.")
    entry = entries[0]
    if entry.get("name") != PLUGIN_NAME:
        raise ValueError("Marketplace plugin name does not match the plugin directory.")
    if entry.get("source", {}).get("path") != f"./plugins/{PLUGIN_NAME}":
        raise ValueError("Marketplace source path is not portable.")

    manifest = _load_json(manifest_path)
    if manifest.get("name") != PLUGIN_NAME or manifest.get("version") != "0.1.1":
        raise ValueError("Plugin manifest identity/version is inconsistent.")
    release_manifest = _load_json(release_manifest_path)
    if release_manifest.get("plugin") != {
        "name": PLUGIN_NAME,
        "version": "0.1.1",
    }:
        raise ValueError("Release manifest identity/version is inconsistent.")
    if release_manifest.get("platform") != "windows-x64":
        raise ValueError("Release manifest platform is inconsistent.")
    if release_manifest.get("delivery", {}).get("clipboard_mime_types") != [
        "text/html",
        "text/plain",
    ]:
        raise ValueError("Release manifest clipboard contract is inconsistent.")
    for skill in (
        "wechat-compose-article",
        "wechat-distill-style",
        "wechat-manage-style-library",
    ):
        skill_root = plugin / "skills" / skill
        for required in (skill_root / "SKILL.md", skill_root / "agents" / "openai.yaml"):
            if not required.is_file():
                raise FileNotFoundError(f"Built skill file is missing: {required}")
        metadata = yaml.safe_load(
            (skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8")
        )
        prompt = metadata.get("interface", {}).get("default_prompt", "")
        if f"${skill}" not in prompt:
            raise ValueError(f"Skill default prompt does not mention ${skill}.")
    return plugin, executable


def validate_contents(distribution: Path) -> None:
    repository_marker = str(REPOSITORY).lower()
    drive_path = re.compile(r"(?i)\b[a-z]:\\(?:users|official account develop|博士科研)\\")
    for path in distribution.rglob("*"):
        if path.is_dir() and path.name.lower() in FORBIDDEN_DIRECTORY_NAMES:
            raise ValueError(f"Forbidden runtime/user directory in distribution: {path}")
        if not path.is_file():
            continue
        if path.suffix.lower() in {".pyc", ".log"}:
            raise ValueError(f"Forbidden generated file in distribution: {path}")
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        lowered = text.lower()
        if repository_marker in lowered or drive_path.search(text):
            raise ValueError(f"Absolute development path leaked into: {path}")
        if any(marker in lowered for marker in ("appid", "appsecret", "proxy_managed")):
            raise ValueError(f"Possible credential/configuration material in: {path}")
        if "[todo:" in lowered:
            raise ValueError(f"Unresolved scaffold placeholder in: {path}")


def relocation_smoke_test(distribution: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="wcs-distribution-") as temporary:
        root = Path(temporary)
        relocated = root / "portable-marketplace"
        shutil.copytree(distribution, relocated)
        plugin = relocated / "plugins" / PLUGIN_NAME
        executable = (
            plugin / "scripts" / "runtime" / "windows-x64" / "wechat-studio.exe"
        )
        workspace = root / "workspace"
        state = root / "state"
        article = root / "article.md"
        article.write_text(
            "---\ntitle: Distribution Smoke Test\n---\n\n"
            "::: lead\nSelf-contained runtime delivery test.\n:::\n\n"
            "The preview must provide **rich-text copy** without source paths.\n",
            encoding="utf-8",
        )

        common = [
            str(executable),
            "--format",
            "json",
            "--workspace",
            str(workspace),
            "--state-root",
            str(state),
        ]
        for command in (
            [*common, "workspace", "init"],
            [
                *common,
                "article",
                "create",
                "--name",
                "Distribution Smoke Test",
                "--mode",
                "layout_only",
                "--project-id",
                "distribution-smoke",
                "--article-file",
                str(article),
            ],
            [*common, "article", "validate", "distribution-smoke"],
            [*common, "article", "render", "distribution-smoke"],
        ):
            completed = _run(command, cwd=root)
            if completed.returncode != 0:
                raise RuntimeError(
                    "Relocated runtime command failed.\n"
                    + completed.stdout
                    + "\n"
                    + completed.stderr
                )
            document = json.loads(completed.stdout)
            if document.get("ok") is not True:
                raise RuntimeError("Relocated runtime returned an unsuccessful result.")

        build = workspace / "articles" / "distribution-smoke" / "build"
        preview = build / "wechat_preview.html"
        delivery = build / "delivery-report.yaml"
        if not preview.is_file() or not delivery.is_file():
            raise FileNotFoundError("Relocated runtime did not generate delivery artifacts.")
        preview_text = preview.read_text(encoding="utf-8")
        if "text/html" not in preview_text or "text/plain" not in preview_text:
            raise ValueError("Preview does not expose both rich-text clipboard MIME types.")


def validate_distribution(distribution: Path) -> dict[str, object]:
    distribution = distribution.resolve()
    plugin, executable = validate_structure(distribution)
    validate_contents(distribution)
    relocation_smoke_test(distribution)
    return {
        "distribution": str(distribution),
        "plugin": str(plugin),
        "runtime": str(executable.parent),
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("distribution", nargs="?", type=Path, default=DEFAULT_DISTRIBUTION)
    args = parser.parse_args()
    result = validate_distribution(args.distribution)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
