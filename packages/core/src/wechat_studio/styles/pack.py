"""Load and validate one self-contained Style Pack directory."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wechat_studio.contracts import ContractValidator
from wechat_studio.errors import StyleInvalidError
from wechat_studio.rendering.components import COMPONENT_NAMES
from wechat_studio.storage.paths import safe_join
from wechat_studio.storage.yaml_io import read_yaml

from .versions import style_directory_name


FORBIDDEN_COMPONENT_MARKUP = re.compile(r"<(?:style|script|link)\b", re.IGNORECASE)
EVENT_HANDLER = re.compile(r"\son[a-z]+\s*=", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class StylePack:
    root: Path
    document: dict[str, Any]
    layout_style: dict[str, Any]
    writing_profile: dict[str, Any] | None

    @property
    def style_id(self) -> str:
        return self.document["style_pack_id"]

    @property
    def version(self) -> str:
        return self.document["version"]

    @property
    def layer(self) -> str:
        return self.document["layer"]

    @property
    def status(self) -> str:
        return self.document["status"]

    @property
    def maturity(self) -> str:
        return self.document["maturity"]

    @property
    def reference(self) -> dict[str, str]:
        return {"id": self.style_id, "version": self.version, "layer": self.layer}

    @property
    def components_directory(self) -> Path:
        return safe_join(self.root, self.document["paths"]["components"])

    @property
    def key(self) -> tuple[str, str, str]:
        return self.layer, self.style_id, self.version

    def fingerprint(self) -> str:
        digest = hashlib.sha256()
        for path in sorted(item for item in self.root.rglob("*") if item.is_file()):
            digest.update(path.relative_to(self.root).as_posix().encode("utf-8"))
            digest.update(b"\x00")
            digest.update(path.read_bytes())
            digest.update(b"\x00")
        return digest.hexdigest()

    def to_record(self) -> dict[str, Any]:
        return {
            "style_pack_id": self.style_id,
            "name": self.document["name"],
            "version": self.version,
            "layer": self.layer,
            "status": self.status,
            "maturity": self.maturity,
            "path": str(self.root),
            "fingerprint": self.fingerprint(),
        }

    @classmethod
    def load(
        cls,
        root: str | Path,
        *,
        expected_layer: str | None = None,
        require_directory_name: bool = False,
        validator: ContractValidator | None = None,
    ) -> "StylePack":
        directory = Path(root).resolve()
        style_path = directory / "style.yaml"
        if not style_path.is_file():
            raise StyleInvalidError(
                f"Style Pack has no style.yaml: {directory}",
                context={"path": str(directory)},
            )
        checked = validator or ContractValidator()
        document = read_yaml(style_path)
        checked.validate_or_raise(document, "style-pack")
        if expected_layer is not None and document["layer"] != expected_layer:
            raise StyleInvalidError(
                f"Style Pack layer does not match its library: {directory}",
                context={
                    "path": str(directory),
                    "expected_layer": expected_layer,
                    "actual_layer": document["layer"],
                },
            )
        expected_name = style_directory_name(
            document["style_pack_id"], document["version"]
        )
        if require_directory_name and directory.name != expected_name:
            raise StyleInvalidError(
                f"Style Pack directory name must be {expected_name}.",
                context={"path": str(directory), "expected_name": expected_name},
            )

        paths = document["paths"]
        if safe_join(directory, paths["style"]) != style_path:
            raise StyleInvalidError(
                "Style Pack paths.style must point to its own style.yaml.",
                context={"path": str(directory), "style_path": paths["style"]},
            )

        required_documents = (
            "sources",
            "placement_rules",
            "article_recipes",
            "validation",
        )
        missing: list[str] = []
        for key in required_documents:
            path = safe_join(directory, paths[key])
            if not path.is_file():
                missing.append(paths[key])
                continue
            value = read_yaml(path)
            if not isinstance(value, dict):
                raise StyleInvalidError(
                    f"Style Pack document must contain a YAML object: {path}",
                    context={"path": str(path), "document": key},
                )
        if missing:
            raise StyleInvalidError(
                f"Style Pack is missing required documents: {directory}",
                context={"path": str(directory), "missing": missing},
            )

        layout_path = safe_join(directory, paths["layout_style"])
        if not layout_path.is_file():
            raise StyleInvalidError(
                f"Style Pack layout profile is missing: {layout_path}",
                context={"path": str(layout_path)},
            )
        layout_style = read_yaml(layout_path)
        checked.validate_or_raise(layout_style, "layout-style")
        layout_reference = document["layout_style"]
        if (
            layout_style["layout_style_id"] != layout_reference["id"]
            or layout_style["version"] != layout_reference["version"]
            or layout_style["version"] != document["version"]
        ):
            raise StyleInvalidError(
                "Style Pack and layout profile identities do not match.",
                context={
                    "style_pack": document["layout_style"],
                    "layout_style_id": layout_style["layout_style_id"],
                    "layout_style_version": layout_style["version"],
                },
            )

        writing_profile: dict[str, Any] | None = None
        writing_reference = document["writing_profile"]
        writing_path_value = paths["writing_profile"]
        if writing_reference is None:
            if writing_path_value is not None:
                raise StyleInvalidError(
                    "paths.writing_profile must be null when writing_profile is null.",
                    context={"path": str(directory)},
                )
        else:
            if writing_path_value is None:
                raise StyleInvalidError(
                    "Style Pack writing profile reference has no path.",
                    context={"path": str(directory)},
                )
            writing_path = safe_join(directory, writing_path_value)
            if not writing_path.is_file():
                raise StyleInvalidError(
                    f"Style Pack writing profile is missing: {writing_path}",
                    context={"path": str(writing_path)},
                )
            writing_profile = read_yaml(writing_path)
            checked.validate_or_raise(writing_profile, "writing-profile")
            if (
                writing_profile["profile_id"] != writing_reference["id"]
                or writing_profile["version"] != writing_reference["version"]
            ):
                raise StyleInvalidError(
                    "Style Pack and writing profile identities do not match.",
                    context={"path": str(directory)},
                )

        components_directory = safe_join(directory, paths["components"])
        if not components_directory.is_dir():
            raise StyleInvalidError(
                f"Style Pack components directory is missing: {components_directory}",
                context={"path": str(components_directory)},
            )
        layout_component_directory = safe_join(
            directory, layout_style["component_directory"]
        )
        if layout_component_directory != components_directory:
            raise StyleInvalidError(
                "layout-style component_directory must match Style Pack paths.components.",
                context={
                    "style_components": str(components_directory),
                    "layout_components": str(layout_component_directory),
                },
            )
        declared = set(layout_style["components"])
        unsupported = sorted(declared - set(COMPONENT_NAMES))
        missing_components = sorted(
            name for name in declared if not (components_directory / f"{name}.html").is_file()
        )
        if unsupported or missing_components:
            raise StyleInvalidError(
                "Style Pack declares invalid or missing components.",
                context={
                    "unsupported": unsupported,
                    "missing": missing_components,
                },
            )
        if declared != set(COMPONENT_NAMES):
            raise StyleInvalidError(
                "MVP Style Packs must provide the complete base-v1 component set.",
                context={
                    "missing": sorted(set(COMPONENT_NAMES) - declared),
                    "extra": sorted(declared - set(COMPONENT_NAMES)),
                },
            )
        unsafe_templates: list[str] = []
        for name in sorted(declared):
            path = components_directory / f"{name}.html"
            value = path.read_text(encoding="utf-8")
            if FORBIDDEN_COMPONENT_MARKUP.search(value) or EVENT_HANDLER.search(value):
                unsafe_templates.append(path.name)
        if unsafe_templates:
            raise StyleInvalidError(
                "Style Pack contains unsafe component templates.",
                context={"components": unsafe_templates},
            )

        return cls(
            root=directory,
            document=document,
            layout_style=layout_style,
            writing_profile=writing_profile,
        )
