"""Deterministic structural validation for one article project."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wechat_studio.composition.anchors import validate_plan_references
from wechat_studio.contracts import ContractValidator
from wechat_studio.errors import ProjectInvalidError
from wechat_studio.projects import ArticleProject, load_article_project
from wechat_studio.storage.yaml_io import read_yaml
from wechat_studio.styles.selection import resolve_project_style_selection

from .delivery import validate_delivery_html


@dataclass(frozen=True, slots=True)
class ArticleProjectValidation:
    project_id: str
    status: str
    checks: tuple[dict[str, Any], ...]
    warnings: tuple[dict[str, Any], ...]

    @property
    def valid(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "status": self.status,
            "checks": [dict(item) for item in self.checks],
            "warnings": [dict(item) for item in self.warnings],
        }

    def raise_for_error(self) -> None:
        failed = [item for item in self.checks if item["status"] == "FAIL"]
        if failed:
            raise ProjectInvalidError(
                f"Article project validation failed: {self.project_id}",
                context={"project_id": self.project_id, "failed_checks": failed},
            )


def _check(
    checks: list[dict[str, Any]],
    name: str,
    status: str,
    detail: str,
    **context: Any,
) -> None:
    record: dict[str, Any] = {"name": name, "status": status, "detail": detail}
    if context:
        record["context"] = context
    checks.append(record)


def validate_article_project(
    project: ArticleProject | str | Path,
) -> ArticleProjectValidation:
    loaded = project if isinstance(project, ArticleProject) else load_article_project(project)
    loaded.reload()
    checks: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    _check(
        checks,
        "contracts",
        "PASS",
        "project.yaml, material manifest, and article plan satisfy schema v1.",
    )

    manifest = loaded.load_manifest()
    plan = loaded.load_plan()
    validate_plan_references(plan, manifest)
    _check(checks, "anchors", "PASS", "All article-plan references resolve.")

    integrity = loaded.material_store.verify()
    failed_materials = [item for item in integrity if item["status"] != "verified"]
    _check(
        checks,
        "material_integrity",
        "FAIL" if failed_materials else "PASS",
        "Material hashes and paths were checked.",
        failures=failed_materials,
    )

    selection = resolve_project_style_selection(loaded)
    _check(
        checks,
        "style_selection",
        "PASS",
        "Pinned layout style and optional writing profile resolve.",
        layout_style=selection.layout.reference,
    )

    article_text = loaded.article_file.read_text(encoding="utf-8")
    if article_text.strip():
        _check(checks, "article_content", "PASS", "article.md contains content.")
    else:
        _check(
            checks,
            "article_content",
            "WARN",
            "article.md is empty; the project is valid but cannot be rendered yet.",
        )
        warnings.append(
            {
                "code": "WCS-PROJECT-006",
                "message": "article.md is empty; add article content before rendering.",
                "context": {"path": str(loaded.article_file)},
            }
        )

    build = loaded.build_directory
    expected = {
        "article": build / "wechat.html",
        "preview": build / "wechat_preview.html",
        "report": build / "delivery-report.yaml",
    }
    present = {name: path.is_file() for name, path in expected.items()}
    if not any(present.values()):
        _check(checks, "build_artifacts", "SKIP", "No generated build exists yet.")
    elif not all(present.values()):
        _check(
            checks,
            "build_artifacts",
            "FAIL",
            "The build directory is incomplete.",
            present=present,
        )
    else:
        article_html = expected["article"].read_text(encoding="utf-8")
        preview_html = expected["preview"].read_text(encoding="utf-8")
        report = read_yaml(expected["report"])
        ContractValidator().validate_or_raise(report, "delivery-report")
        delivery = validate_delivery_html(
            article_html,
            preview_html,
            expected_image_count=len(report.get("images", [])),
        )
        _check(
            checks,
            "build_artifacts",
            "PASS" if delivery.status == "PASS" else "FAIL",
            "Generated article and preview were checked without browser screenshots.",
            delivery_checks=[dict(item) for item in delivery.checks],
        )
        identity_matches = bool(
            report.get("project_id") == loaded.project_id
            and report.get("build_id") == loaded.document["generation"]["last_build_id"]
        )
        _check(
            checks,
            "build_identity",
            "PASS" if identity_matches else "FAIL",
            "Delivery report matches the project's pinned generation.",
            report_project_id=report.get("project_id"),
            report_build_id=report.get("build_id"),
            project_build_id=loaded.document["generation"]["last_build_id"],
        )

    status = "FAIL" if any(item["status"] == "FAIL" for item in checks) else "PASS"
    return ArticleProjectValidation(
        project_id=loaded.project_id,
        status=status,
        checks=tuple(checks),
        warnings=tuple(warnings),
    )
