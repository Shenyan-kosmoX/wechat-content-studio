"""Export and import shareable WeChat Content Studio style assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import yaml


BUNDLE_SCHEMA = "1.0"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file()) if root.is_dir() else []


def _manifest(workspace: Path) -> dict[str, object]:
    entries: list[dict[str, str]] = []
    for relative_root in ("styles/private", "writing-profiles", "presets"):
        root = workspace / relative_root
        for path in _files(root):
            relative = path.relative_to(workspace).as_posix()
            entries.append({"path": relative, "sha256": _sha256(path)})
    return {
        "style_bundle_schema_version": BUNDLE_SCHEMA,
        "source": "wechat-content-studio",
        "assets": entries,
    }


def export_bundle(workspace: Path, output: Path) -> dict[str, object]:
    workspace = workspace.resolve()
    output = output.resolve()
    if output.suffix.lower() != ".zip":
        raise ValueError("Bundle output must be a .zip file.")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = _manifest(workspace)
    temporary = output.with_suffix(output.suffix + ".tmp")
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            bundle.writestr("style-bundle.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            for item in manifest["assets"]:
                path = workspace / item["path"]
                bundle.write(path, item["path"])
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return {"status": "PASS", "bundle": str(output), "assets": len(manifest["assets"])}


def _safe_member(name: str) -> Path:
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or path.name == "":
        raise ValueError(f"Unsafe bundle member: {name}")
    if not (name.startswith("styles/private/") or name.startswith("writing-profiles/") or name.startswith("presets/")):
        raise ValueError(f"Unsupported bundle member: {name}")
    return path


def import_bundle(workspace: Path, source: Path) -> dict[str, object]:
    workspace = workspace.resolve()
    with zipfile.ZipFile(source, "r") as bundle:
        try:
            manifest = json.loads(bundle.read("style-bundle.json").decode("utf-8"))
        except (KeyError, json.JSONDecodeError) as exc:
            raise ValueError("Bundle is missing a valid style-bundle.json.") from exc
        if manifest.get("style_bundle_schema_version") != BUNDLE_SCHEMA:
            raise ValueError("Unsupported style bundle schema version.")
        assets = manifest.get("assets")
        if not isinstance(assets, list):
            raise ValueError("Bundle assets manifest is invalid.")
        checked: list[tuple[str, bytes]] = []
        for item in assets:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                raise ValueError("Bundle asset entry is invalid.")
            relative = _safe_member(item["path"])
            data = bundle.read(relative.as_posix())
            if hashlib.sha256(data).hexdigest() != item.get("sha256"):
                raise ValueError(f"Checksum mismatch: {relative.as_posix()}")
            checked.append((relative.as_posix(), data))
        conflicts = [path for path, _ in checked if (workspace / path).exists()]
        if conflicts:
            raise FileExistsError("Refusing to overwrite existing assets: " + ", ".join(conflicts))
        for relative, data in checked:
            destination = workspace / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
    return {"status": "PASS", "bundle": str(source.resolve()), "assets": len(checked)}


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("--workspace", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    import_cmd = sub.add_parser("import")
    import_cmd.add_argument("--workspace", type=Path, required=True)
    import_cmd.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    result = export_bundle(args.workspace, args.output) if args.command == "export" else import_bundle(args.workspace, args.source)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
