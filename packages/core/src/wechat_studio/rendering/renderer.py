"""Render legacy fixtures and atomically build validated article projects."""

from __future__ import annotations

import hashlib
import html
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from wechat_studio.composition.anchors import validate_plan_references
from wechat_studio.composition.locks import exclusive_lock
from wechat_studio.contracts import ContractValidator
from wechat_studio.errors import DeliveryValidationError, RenderError
from wechat_studio.projects.project import ArticleProject
from wechat_studio.storage.atomic import atomic_replace_directory
from wechat_studio.storage.yaml_io import write_yaml_atomic
from wechat_studio.validation.delivery import DeliveryValidation, validate_delivery_html

from . import legacy_v1
from .components import ComponentCatalog
from .images import ProjectImageResolver, image_report_record, render_image_checklist
from .markdown_subset import MarkdownRender, render_markdown_file
from .preview import render_product_preview


ARTICLE_ROOT_STYLE = legacy_v1.ARTICLE_ROOT_STYLE


@dataclass(frozen=True, slots=True)
class BuildResult:
    project_id: str
    build_id: str
    status: str
    build_directory: Path
    generated_files: tuple[Path, ...]
    report: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "build_id": self.build_id,
            "status": self.status,
            "build_directory": str(self.build_directory),
            "generated_files": [str(path) for path in self.generated_files],
            "report": self.report,
        }


def _now() -> datetime:
    return datetime.now().astimezone()


def _identifier(prefix: str, moment: datetime) -> str:
    return f"{prefix}-{moment:%Y%m%d-%H%M%S}-{uuid4().hex[:6].upper()}"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file_record(
    project_root: Path,
    path: Path,
    role: str,
    *,
    reported_path: str | None = None,
) -> dict[str, object]:
    return {
        "role": role,
        "path": reported_path
        or path.resolve().relative_to(project_root.resolve()).as_posix(),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }


def render_article_root(article_html: str, root_id: str) -> str:
    return legacy_v1.render_article_root(article_html, root_id)


def render_document_from_article(title: str, article_html: str) -> str:
    return legacy_v1.render_document_from_article(title, article_html)


def render_legacy_delivery(
    source: str | Path,
    destination: str | Path,
    *,
    preview: str | Path | None = None,
    components_directory: str | Path | None = None,
) -> tuple[Path, Path]:
    source_path = Path(source)
    destination_path = Path(destination)
    components = (
        Path(components_directory)
        if components_directory is not None
        else ComponentCatalog.load().directory
    )
    try:
        title, article = legacy_v1.render_article(source_path, components)
        article_document = legacy_v1.render_document_from_article(title, article)
        preview_document = legacy_v1.render_preview_document_from_article(title, article)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_text(article_document, encoding="utf-8")
        preview_path = Path(preview) if preview is not None else destination_path.with_name(
            "wechat_preview.html"
        )
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_text(preview_document, encoding="utf-8")
        return destination_path, preview_path
    except Exception as exc:
        if isinstance(exc, RenderError):
            raise
        raise RenderError(
            f"Legacy V1 rendering failed for {source_path}.",
            context={"source": str(source_path), "reason": str(exc)},
        ) from exc


def _validate_material_integrity(project: ArticleProject) -> None:
    failures = [
        record
        for record in project.material_store.verify()
        if record["status"] != "verified"
    ]
    if failures:
        raise RenderError(
            "Article materials failed integrity verification.",
            context={"project_id": project.project_id, "materials": failures},
        )


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def _build_report(
    *,
    project: ArticleProject,
    build_id: str,
    report_id: str,
    generated_at: str,
    staging: Path,
    rendered: MarkdownRender,
    validation: DeliveryValidation,
) -> dict[str, object]:
    inputs = [
        _file_record(project.root, project.article_file, "article"),
        _file_record(project.root, project.plan_file, "article_plan"),
        _file_record(project.root, project.manifest_file, "material_manifest"),
    ]
    outputs = [
        _file_record(
            project.root,
            staging / "wechat.html",
            "wechat_html",
            reported_path="build/wechat.html",
        ),
        _file_record(
            project.root,
            staging / "wechat_preview.html",
            "preview_html",
            reported_path="build/wechat_preview.html",
        ),
        _file_record(
            project.root,
            staging / "image-checklist.md",
            "image_checklist",
            reported_path="build/image-checklist.md",
        ),
    ]
    for asset in sorted((staging / "assets").glob("**/*")) if (staging / "assets").exists() else ():
        if asset.is_file():
            outputs.append(
                _file_record(
                    project.root,
                    asset,
                    "image_asset",
                    reported_path=f"build/{asset.relative_to(staging).as_posix()}",
                )
            )

    risks: list[dict[str, object]] = []
    for image in rendered.images:
        if image.delivery_status != "ready":
            risks.append(
                {
                    "code": "WCS-IMAGE-001",
                    "severity": "warning",
                    "message": "图片需要用户在微信公众号后台粘贴后确认。",
                    "context": {
                        "image_id": image.image_id,
                        "source": image.source,
                        "fallback": image.fallback,
                    },
                }
            )

    return {
        "delivery_report_schema_version": "1.0",
        "report_id": report_id,
        "project_id": project.project_id,
        "build_id": build_id,
        "generated_at": generated_at,
        "status": "READY_FOR_USER_WECHAT_VALIDATION",
        "inputs": inputs,
        "style": project.document["style"],
        "outputs": outputs,
        "checks": [dict(check) for check in validation.checks],
        "risks": risks,
        "images": [image_report_record(image) for image in rendered.images],
        "validation": {
            "local_status": validation.status,
            "wechat_status": "AWAITING_USER_VALIDATION",
            "confirmed_by_user": False,
            "confirmed_at": None,
            "notes": "本地结构与富文本复制实现已检查；由用户自行在微信公众号后台粘贴验证，不要求截图。",
        },
    }


def build_article_project(
    project: ArticleProject,
    *,
    components_directory: str | Path | None = None,
) -> BuildResult:
    moment = _now()
    build_id = _identifier("BUILD", moment)
    report_id = build_id.replace("BUILD-", "REPORT-", 1)
    generated_at = moment.isoformat(timespec="seconds")
    build_lock = (
        project.workspace_paths.locks / f"build-{project.project_id}.lock"
        if project.workspace_paths is not None
        else project.root / ".build.lock"
    )

    with exclusive_lock(build_lock, timeout_seconds=2.0):
        project.reload()
        manifest = project.load_manifest()
        plan = project.load_plan()
        validate_plan_references(plan, manifest)
        _validate_material_integrity(project)
        if not project.article_file.read_text(encoding="utf-8").strip():
            raise RenderError(
                "Article Markdown is empty.",
                context={"project_id": project.project_id, "path": str(project.article_file)},
            )

        staging = Path(
            tempfile.mkdtemp(
                prefix=".build.",
                suffix=".tmp",
                dir=project.root,
            )
        )
        try:
            if components_directory is not None:
                catalog = ComponentCatalog.load(components_directory)
            else:
                from wechat_studio.styles.selection import (
                    resolve_project_style_selection,
                )

                style_selection = resolve_project_style_selection(project)
                catalog = ComponentCatalog.load(
                    style_selection.layout.components_directory
                )
            resolver = ProjectImageResolver(
                project_root=project.root,
                build_directory=staging,
                manifest=manifest,
                plan=plan,
            )
            rendered = render_markdown_file(
                project.article_file,
                components=catalog,
                image_resolver=resolver,
            )
            article_document = render_document_from_article(
                rendered.title, rendered.article_html
            )
            copy_root = render_article_root(rendered.article_html, "wechat-copy-root")
            preview_document = render_product_preview(
                rendered.title,
                copy_root,
                has_fallback_images=any(
                    image.fallback_required for image in rendered.images
                ),
            )
            checklist = render_image_checklist(rendered.images)

            _write_text(staging / "wechat.html", article_document)
            _write_text(staging / "wechat_preview.html", preview_document)
            _write_text(staging / "image-checklist.md", checklist)

            validation = validate_delivery_html(
                article_document,
                preview_document,
                expected_image_count=len(rendered.images),
            )
            validation.raise_for_error()
            report = _build_report(
                project=project,
                build_id=build_id,
                report_id=report_id,
                generated_at=generated_at,
                staging=staging,
                rendered=rendered,
                validation=validation,
            )
            contract_validator = ContractValidator()
            contract_validator.validate_or_raise(report, "delivery-report")
            write_yaml_atomic(
                staging / "delivery-report.yaml",
                report,
                validator=lambda value: contract_validator.validate_or_raise(
                    value, "delivery-report"
                ),
            )

            atomic_replace_directory(
                project.build_directory,
                staging,
                after_replace=lambda: project.record_build(
                    build_id=build_id,
                    status="READY_FOR_USER_WECHAT_VALIDATION",
                ),
            )
            generated_files = tuple(
                project.build_directory / name
                for name in (
                    "wechat.html",
                    "wechat_preview.html",
                    "image-checklist.md",
                    "delivery-report.yaml",
                )
            )
            return BuildResult(
                project_id=project.project_id,
                build_id=build_id,
                status="READY_FOR_USER_WECHAT_VALIDATION",
                build_directory=project.build_directory,
                generated_files=generated_files,
                report=report,
            )
        except Exception as exc:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            if isinstance(exc, (RenderError, DeliveryValidationError)):
                raise
            raise RenderError(
                f"Article build failed for {project.project_id}.",
                context={"project_id": project.project_id, "reason": str(exc)},
            ) from exc
