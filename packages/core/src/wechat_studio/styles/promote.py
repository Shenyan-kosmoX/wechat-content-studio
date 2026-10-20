"""Import candidate packs and promote confirmed candidates to private stable versions."""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from wechat_studio.contracts import ContractValidator
from wechat_studio.errors import StyleConflictError, StylePromotionError
from wechat_studio.storage.paths import WorkspacePaths
from wechat_studio.storage.yaml_io import read_yaml, write_yaml_atomic

from .pack import StylePack
from .versions import parse_semver, stable_version, style_directory_name


def _copy_directory_atomic(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise StyleConflictError(
            f"Style Pack version already exists: {destination.name}",
            context={"path": str(destination)},
        )
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
    )
    try:
        shutil.rmtree(staging)
        shutil.copytree(source, staging)
        os.replace(staging, destination)
        return destination
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise


def import_candidate(source: str | Path, paths: WorkspacePaths) -> StylePack:
    candidate = StylePack.load(source)
    if candidate.status != "candidate":
        raise StylePromotionError(
            "Only status=candidate Style Packs may enter the imports library.",
            context={"path": str(candidate.root), "status": candidate.status},
        )
    destination = paths.imported_styles / style_directory_name(
        candidate.style_id, candidate.version
    )
    _copy_directory_atomic(candidate.root, destination)
    try:
        return StylePack.load(destination, require_directory_name=True)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def _rewrite_promoted_documents(
    directory: Path,
    *,
    target_version: str,
    candidate: StylePack,
) -> None:
    validator = ContractValidator()
    style_path = directory / "style.yaml"
    style = read_yaml(style_path)
    style["version"] = target_version
    style["layer"] = "private"
    style["status"] = "active"
    style["maturity"] = (
        "validated" if candidate.maturity == "validated" else "established"
    )
    style["layout_style"]["version"] = target_version
    if style["writing_profile"] is not None:
        style["writing_profile"]["version"] = target_version
    style["provenance"]["parent_version"] = candidate.version
    extensions = style.setdefault("extensions", {})
    promotion = extensions.setdefault("shenyan.promotion", {})
    promotion["confirmed_by_user"] = True
    promotion["promoted_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    write_yaml_atomic(
        style_path,
        style,
        validator=lambda value: validator.validate_or_raise(value, "style-pack"),
    )

    layout_path = directory / style["paths"]["layout_style"]
    layout = read_yaml(layout_path)
    layout["version"] = target_version
    layout["status"] = "validated" if style["maturity"] == "validated" else "established"
    write_yaml_atomic(
        layout_path,
        layout,
        validator=lambda value: validator.validate_or_raise(value, "layout-style"),
    )

    writing_path_value = style["paths"]["writing_profile"]
    if writing_path_value is not None:
        writing_path = directory / writing_path_value
        writing = read_yaml(writing_path)
        writing["version"] = target_version
        writing["status"] = "validated" if style["maturity"] == "validated" else "established"
        write_yaml_atomic(
            writing_path,
            writing,
            validator=lambda value: validator.validate_or_raise(value, "writing-profile"),
        )


def promote_candidate(
    candidate: StylePack | str | Path,
    paths: WorkspacePaths,
    *,
    confirmed_by_user: bool,
    target_version: str | None = None,
) -> StylePack:
    source = candidate if isinstance(candidate, StylePack) else StylePack.load(candidate)
    if source.status != "candidate":
        raise StylePromotionError(
            "Only candidate Style Packs can be promoted.",
            context={"path": str(source.root), "status": source.status},
        )
    if not confirmed_by_user:
        raise StylePromotionError(
            "Candidate promotion requires explicit user confirmation.",
            context={"style_id": source.style_id, "version": source.version},
        )
    version = target_version or stable_version(source.version)
    parsed = parse_semver(version)
    if not parsed.stable:
        raise StylePromotionError(
            "Promoted Style Pack versions must be stable semantic versions.",
            context={"target_version": version},
        )
    destination = paths.private_styles / style_directory_name(source.style_id, version)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise StyleConflictError(
            f"Private Style Pack version already exists: {source.style_id} {version}",
            context={"path": str(destination)},
        )
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
    )
    try:
        shutil.rmtree(staging)
        shutil.copytree(source.root, staging)
        _rewrite_promoted_documents(
            staging,
            target_version=version,
            candidate=source,
        )
        StylePack.load(staging, expected_layer="private")
        os.replace(staging, destination)
        return StylePack.load(
            destination,
            expected_layer="private",
            require_directory_name=True,
        )
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise
