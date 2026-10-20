"""Build schema-valid candidate profiles and Style Packs from aggregates."""

from __future__ import annotations

import html
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from wechat_studio.composition.ids import PROJECT_ID_RE
from wechat_studio.contracts import ContractValidator
from wechat_studio.errors import (
    DistillationInsufficientEvidenceError,
    DistillationInvalidError,
    StyleConflictError,
)
from wechat_studio.rendering.components import COMPONENT_NAMES, ComponentCatalog
from wechat_studio.storage.atomic import atomic_write_text
from wechat_studio.storage.paths import resolve_resource_root
from wechat_studio.storage.yaml_io import write_yaml_atomic
from wechat_studio.styles.pack import StylePack
from wechat_studio.styles.versions import parse_semver, style_directory_name

from .confidence import MaturityAssessment, assess_candidate_maturity
from .html_evidence import parse_style


_STYLE_ATTRIBUTE = re.compile(
    r'(?P<prefix><[^>]*?\bstyle=")(?P<style>[^"]*)(?P<suffix>")',
    re.IGNORECASE,
)
_SAFE_STYLE_PROPERTIES = {
    "background-color",
    "border",
    "border-bottom",
    "border-bottom-color",
    "border-bottom-style",
    "border-bottom-width",
    "border-left",
    "border-left-color",
    "border-left-style",
    "border-left-width",
    "border-radius",
    "border-right",
    "border-right-color",
    "border-right-style",
    "border-right-width",
    "border-top",
    "border-top-color",
    "border-top-style",
    "border-top-width",
    "color",
    "display",
    "font-family",
    "font-size",
    "font-style",
    "font-weight",
    "height",
    "letter-spacing",
    "line-height",
    "margin",
    "margin-bottom",
    "margin-left",
    "margin-right",
    "margin-top",
    "max-width",
    "overflow-wrap",
    "padding",
    "padding-bottom",
    "padding-left",
    "padding-right",
    "padding-top",
    "text-align",
    "text-decoration",
    "white-space",
    "width",
    "word-break",
}
_COMPONENT_TARGET_STYLE_INDEX = {
    "image": 1,
    "list": 1,
    "section_title": 1,
}
_DEFAULT_POSITIONS = {
    "lead": ["opening"],
    "ending": ["ending"],
    "paragraph": ["opening", "middle", "ending"],
    "section_title": ["middle"],
    "sub_title": ["middle"],
    "key_sentence": ["middle"],
    "quote": ["middle"],
    "image": ["middle"],
    "caption": ["middle"],
    "divider": ["middle"],
    "code": ["middle"],
    "list": ["middle"],
}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class CandidateBuildResult:
    kind: str
    path: Path
    document: dict[str, Any]
    maturity: MaturityAssessment
    style_pack: StylePack | None = None

    @property
    def reference(self) -> dict[str, str]:
        if self.kind == "style_pack":
            return {
                "id": self.document["style_pack_id"],
                "version": self.document["version"],
                "layer": self.document["layer"],
            }
        return {
            "id": self.document["profile_id"],
            "version": self.document["version"],
            "layer": "project",
        }


def _validate_identity(style_id: str, version: str, storage: str) -> None:
    if not PROJECT_ID_RE.fullmatch(style_id):
        raise DistillationInvalidError(
            f"Invalid candidate style id: {style_id}",
            context={"style_id": style_id},
        )
    parsed = parse_semver(version)
    if parsed.stable or "candidate" not in parsed.prerelease:
        raise DistillationInvalidError(
            "Candidate versions must use a -candidate prerelease suffix.",
            context={"version": version, "example": "0.1.0-candidate.1"},
        )
    if storage not in {"project", "imports"}:
        raise DistillationInvalidError(
            "Candidate storage must be project or imports.",
            context={"storage": storage},
        )


def _unique_strings(values: Iterable[str], *, limit: int = 48) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and len(normalized) <= limit and normalized not in result:
            result.append(normalized)
    return result


def _writing_profile(
    aggregate: Mapping[str, Any],
    *,
    profile_id: str,
    name: str,
    version: str,
    maturity: str,
    tags: list[str],
    storage: str,
) -> dict[str, Any] | None:
    writing = aggregate.get("writing")
    if not isinstance(writing, Mapping):
        return None
    document = {
        "writing_profile_schema_version": "1.0",
        "profile_id": profile_id,
        "name": f"{name} 写作档案",
        "version": version,
        "status": maturity,
        "description": "从已确认样本的结构化文本证据生成的候选写作档案。",
        "tags": _unique_strings([*tags, "distilled", "candidate"]),
        "tone": {
            "traits": _unique_strings(writing.get("tone_traits", ["结构清晰"]), limit=80),
            "avoid": _unique_strings(
                writing.get("tone_avoid", ["复制参考样本原句或标志性表达"]),
                limit=120,
            ),
        },
        "narrative_rhythm": {
            "pace": writing.get("pace", "measured"),
            "sentence_variation": writing.get("sentence_variation", "medium"),
            "notes": "仅描述跨样本可复用的高层节奏，不包含参考原文。",
        },
        "paragraph_length": {
            "minimum_characters": int(writing.get("paragraph_minimum", 0)),
            "maximum_characters": max(1, int(writing.get("paragraph_maximum", 180))),
        },
        "argument_structure": list(
            writing.get("argument_structure", ["围绕核心主题逐层展开"])
        ),
        "opening_patterns": list(writing.get("opening_patterns", ["context_first_opening"])),
        "ending_patterns": list(writing.get("ending_patterns", ["concise_conclusion"])),
        "evidence": [dict(item) for item in writing.get("evidence", [])],
        "extensions": {
            "shenyan.distillation": {
                "candidate": True,
                "storage": storage,
                "sample_count": len(writing.get("sample_ids", [])),
                "copyright_boundary": "high-level-features-only",
            }
        },
    }
    ContractValidator().validate_or_raise(document, "writing-profile")
    return document


def _safe_evidence_style(style: Mapping[str, Any]) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for property_name, raw_value in style.items():
        name = str(property_name).lower().strip()
        value = str(raw_value).strip()
        lowered = value.lower()
        if name not in _SAFE_STYLE_PROPERTIES or not value:
            continue
        if any(
            marker in lowered
            for marker in ("url(", "expression(", "javascript:", "data:", "!important")
        ):
            continue
        if any(character in value for character in ('"', "'", "<", ">", "\x00")):
            continue
        sanitized[name] = value
    return sanitized


def _serialize_style(style: Mapping[str, str]) -> str:
    return ";".join(f"{name}:{value}" for name, value in style.items()) + ";"


def _merge_component_style(
    template: str,
    component: str,
    evidence_style: Mapping[str, Any],
) -> str:
    matches = list(_STYLE_ATTRIBUTE.finditer(template))
    if not matches:
        return template
    target_index = min(_COMPONENT_TARGET_STYLE_INDEX.get(component, 0), len(matches) - 1)
    target = matches[target_index]
    merged = parse_style(target.group("style"))
    merged.update(_safe_evidence_style(evidence_style))
    replacement = (
        target.group("prefix")
        + html.escape(_serialize_style(merged), quote=True)
        + target.group("suffix")
    )
    return template[: target.start()] + replacement + template[target.end() :]


def _placement_rules(layout: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    profiles = layout.get("component_profiles", {})
    rules: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for component, profile in sorted(profiles.items()):
        if component not in COMPONENT_NAMES:
            continue
        token = component.replace("_", "-").upper()
        rule_id = f"PLACE-{token}-001"
        positions = list(profile.get("positions") or _DEFAULT_POSITIONS[component])
        rules.append(
            {
                "rule_id": rule_id,
                "component": component,
                "preferred_positions": positions,
                "forbidden_positions": [],
                "maximum_consecutive": 3
                if component == "image"
                else (20 if component == "paragraph" else 1),
            }
        )
        evidence.append(
            {
                "rule_id": rule_id,
                "meaning": f"{component} 在样本中的常见位置为 {', '.join(positions)}。",
                "sample_ids": list(profile["sample_ids"]),
                "confidence": profile["confidence"],
            }
        )
    return rules, evidence


def _layout_style(
    aggregate: Mapping[str, Any],
    *,
    style_id: str,
    name: str,
    version: str,
    maturity: str,
    tags: list[str],
    article_types: list[str],
    storage: str,
) -> dict[str, Any] | None:
    layout = aggregate.get("layout")
    if not isinstance(layout, Mapping):
        return None
    rules, position_evidence = _placement_rules(layout)
    evidence = [dict(item) for item in layout.get("evidence", [])]
    evidence.extend(position_evidence)
    document = {
        "layout_style_schema_version": "1.0",
        "layout_style_id": style_id,
        "name": f"{name} 排版候选",
        "version": version,
        "status": maturity,
        "description": "从正文 HTML 与 inline-style 证据生成，等待用户预览和公众号粘贴验证。",
        "tags": _unique_strings([*tags, "distilled", "candidate", "inline-style"]),
        "article_types": article_types,
        "root": dict(layout["root"]),
        "component_directory": "components",
        "components": list(COMPONENT_NAMES),
        "placement_rules": rules,
        "evidence": evidence,
        "extensions": {
            "shenyan.distillation": {
                "candidate": True,
                "storage": storage,
                "sample_count": len(layout.get("sample_ids", [])),
                "conflicts": list(layout.get("conflicts", [])),
                "component_profiles": dict(layout.get("component_profiles", {})),
            }
        },
    }
    ContractValidator().validate_or_raise(document, "layout-style")
    return document


def _write_components(
    destination: Path,
    layout: Mapping[str, Any],
    *,
    base_components: str | Path | None,
) -> None:
    catalog = ComponentCatalog.load(
        base_components or (resolve_resource_root() / "components" / "base-v1")
    )
    profiles = layout.get("component_profiles", {})
    destination.mkdir(parents=True, exist_ok=True)
    for component in COMPONENT_NAMES:
        template = catalog.get(component)
        profile = profiles.get(component)
        if isinstance(profile, Mapping):
            template = _merge_component_style(template, component, profile.get("style", {}))
        atomic_write_text(destination / f"{component}.html", template.strip() + "\n")


def _sources_document(
    aggregate: Mapping[str, Any],
    *,
    publisher_or_author: str,
    storage: str,
) -> dict[str, Any]:
    return {
        "sources_schema_version": "1.0",
        "publisher_or_author": publisher_or_author,
        "sample_scope": {
            "accepted_samples": int(aggregate.get("usable_sample_count", 0)),
            "submitted_samples": int(aggregate.get("sample_count", 0)),
            "article_types": list(aggregate.get("article_types", [])),
            "evidence_types": [
                value
                for value, available in (
                    ("writing", aggregate.get("writing") is not None),
                    ("body_html_and_inline_style", aggregate.get("layout") is not None),
                )
                if available
            ],
        },
        "samples": [
            {"sample_id": sample_id, "storage_policy": "evidence-identifier-only"}
            for sample_id in aggregate.get("sample_ids", [])
        ],
        "storage": storage,
        "copyright_boundary": "只保留高层可复用特征、统计摘要和证据 ID，不复制参考文章正文。",
    }


def _article_recipes(layout: Mapping[str, Any], article_types: list[str]) -> dict[str, Any]:
    profiles = layout.get("component_profiles", {})
    preferred = [component for component in COMPONENT_NAMES if component in profiles]
    sequence = preferred or ["lead", "paragraph", "section_title", "paragraph", "ending"]
    return {
        "article_recipes_schema_version": "1.0",
        "recipes": {
            article_type: {
                "sequence": sequence,
                "status": "candidate",
                "note": "候选配方仅来自已观察组件；未观察组件仍保留安全模板但不自动使用。",
            }
            for article_type in (article_types or ["other"])
        },
    }


def _validation_document(
    *,
    aggregate: Mapping[str, Any],
    maturity: MaturityAssessment,
) -> dict[str, Any]:
    return {
        "validation_schema_version": "1.0",
        "local": {
            "status": "PASS",
            "checks": {
                "schema_valid": True,
                "component_count": len(COMPONENT_NAMES),
                "inline_style_only": True,
                "sample_traceability": True,
                "conflict_count": int(aggregate.get("conflict_count", 0)),
            },
        },
        "wechat": {
            "status": "AWAITING_USER_VALIDATION",
            "screenshot_required": False,
            "note": "用户自行在微信公众号后台粘贴验证；本地检查不代表微信端验证。",
        },
        "maturity_assessment": maturity.to_dict(),
    }


def build_candidate(
    aggregate: Mapping[str, Any],
    destination_root: str | Path,
    *,
    style_id: str,
    name: str,
    version: str = "0.1.0-candidate.1",
    storage: str = "project",
    publisher_or_author: str = "",
    tags: Iterable[str] = (),
    reviewed_for_established: bool = False,
    base_components: str | Path | None = None,
) -> CandidateBuildResult:
    """Create a project/import candidate without touching the private library."""

    _validate_identity(style_id, version, storage)
    if aggregate.get("distillation_aggregate_version") != "1.0":
        raise DistillationInvalidError(
            "Unsupported or missing distillation aggregate version.",
            context={"actual": aggregate.get("distillation_aggregate_version")},
        )
    has_writing = isinstance(aggregate.get("writing"), Mapping)
    has_layout = isinstance(aggregate.get("layout"), Mapping)
    if not has_writing and not has_layout:
        raise DistillationInsufficientEvidenceError(
            "No usable writing or layout evidence is available.",
            context={"sample_count": aggregate.get("sample_count", 0)},
        )

    article_types = _unique_strings(aggregate.get("article_types", []))
    if not article_types:
        article_types = ["other"]
    maturity = assess_candidate_maturity(
        usable_sample_count=int(aggregate.get("usable_sample_count", 0)),
        article_type_count=len(article_types),
        has_writing_evidence=has_writing,
        has_layout_evidence=has_layout,
        conflict_count=int(aggregate.get("conflict_count", 0)),
        reviewed_for_established=reviewed_for_established,
    )
    normalized_tags = _unique_strings(tags)
    profile_id = f"{style_id}-writing"
    writing = _writing_profile(
        aggregate,
        profile_id=profile_id,
        name=name,
        version=version,
        maturity=maturity.maturity,
        tags=normalized_tags,
        storage=storage,
    )
    root = Path(destination_root).resolve()
    root.mkdir(parents=True, exist_ok=True)

    if not has_layout:
        assert writing is not None
        destination = root / "writing-profiles" / f"{profile_id}-v{version}.yaml"
        if destination.exists():
            raise StyleConflictError(
                f"Candidate writing profile already exists: {destination.name}",
                context={"path": str(destination)},
            )
        write_yaml_atomic(
            destination,
            writing,
            validator=lambda value: ContractValidator().validate_or_raise(
                value, "writing-profile"
            ),
        )
        return CandidateBuildResult(
            kind="writing_profile",
            path=destination,
            document=writing,
            maturity=maturity,
        )

    layout = _layout_style(
        aggregate,
        style_id=style_id,
        name=name,
        version=version,
        maturity=maturity.maturity,
        tags=normalized_tags,
        article_types=article_types,
        storage=storage,
    )
    assert layout is not None
    destination = root / style_directory_name(style_id, version)
    if destination.exists():
        raise StyleConflictError(
            f"Candidate Style Pack already exists: {destination.name}",
            context={"path": str(destination)},
        )
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", suffix=".tmp", dir=root)
    )
    timestamp = _now()
    evidence_scope = "writing_and_layout" if has_writing else "layout_only"
    style_document = {
        "style_pack_schema_version": "1.0",
        "style_pack_id": style_id,
        "name": name,
        "version": version,
        "layer": "project",
        "status": "candidate",
        "maturity": maturity.maturity,
        "tags": _unique_strings([*normalized_tags, "distilled", "candidate"]),
        "article_types": article_types,
        "layout_style": {"id": style_id, "version": version},
        "writing_profile": (
            {"id": profile_id, "version": version} if writing is not None else None
        ),
        "paths": {
            "style": "style.yaml",
            "layout_style": "layout-style.yaml",
            "writing_profile": "writing-profile.yaml" if writing is not None else None,
            "sources": "sources.yaml",
            "placement_rules": "placement-rules.yaml",
            "article_recipes": "article-recipes.yaml",
            "validation": "validation.yaml",
            "components": "components",
        },
        "provenance": {
            "created_at": timestamp,
            "sample_ids": list(aggregate.get("sample_ids", [])),
            "evidence_scope": evidence_scope,
            "parent_version": None,
        },
        "extensions": {
            "shenyan.distillation": {
                "storage": storage,
                "candidate": True,
                "maturity_assessment": maturity.to_dict(),
            }
        },
    }
    validator = ContractValidator()
    validator.validate_or_raise(style_document, "style-pack")

    try:
        write_yaml_atomic(staging / "style.yaml", style_document)
        write_yaml_atomic(staging / "layout-style.yaml", layout)
        if writing is not None:
            write_yaml_atomic(staging / "writing-profile.yaml", writing)
        write_yaml_atomic(
            staging / "sources.yaml",
            _sources_document(
                aggregate,
                publisher_or_author=publisher_or_author,
                storage=storage,
            ),
        )
        write_yaml_atomic(
            staging / "placement-rules.yaml",
            {
                "placement_rules_schema_version": "1.0",
                "rules": layout["placement_rules"],
                "evidence": [
                    item for item in layout["evidence"] if item["rule_id"].startswith("PLACE-")
                ],
            },
        )
        write_yaml_atomic(
            staging / "article-recipes.yaml",
            _article_recipes(aggregate["layout"], article_types),
        )
        write_yaml_atomic(
            staging / "validation.yaml",
            _validation_document(aggregate=aggregate, maturity=maturity),
        )
        _write_components(
            staging / "components",
            aggregate["layout"],
            base_components=base_components,
        )
        StylePack.load(staging, expected_layer="project", validator=validator)
        os.replace(staging, destination)
        pack = StylePack.load(
            destination,
            expected_layer="project",
            require_directory_name=True,
            validator=validator,
        )
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise

    return CandidateBuildResult(
        kind="style_pack",
        path=destination,
        document=style_document,
        maturity=maturity,
        style_pack=pack,
    )
