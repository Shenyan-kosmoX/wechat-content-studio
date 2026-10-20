"""Resolve article image references without hiding delivery uncertainty."""

from __future__ import annotations

import html
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import unquote, urlparse

from wechat_studio.errors import MaterialNotFoundError, RenderError
from wechat_studio.storage.atomic import atomic_write_bytes
from wechat_studio.storage.paths import safe_join

from .inline import safe_web_url
from .markdown_subset import ResolvedImage


WECHAT_IMAGE_HOSTS = {
    "mmbiz.qpic.cn",
    "mmbiz.qlogo.cn",
}


def _is_wechat_image_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    host = hostname.lower().rstrip(".")
    return host in WECHAT_IMAGE_HOSTS or host.endswith(".qpic.cn")


def _url_filename(source: str, index: int) -> str:
    path = unquote(urlparse(source).path)
    name = Path(path).name.strip()
    return name or f"image-{index:03d}"


def _fallback_text(image_id: str, filename: str, caption: str) -> str:
    label = caption.strip() or "无图注"
    return f"【请插入 {image_id}｜{filename}｜{label}】"


class ProjectImageResolver:
    """Resolve URLs and registered local materials for one project build."""

    def __init__(
        self,
        *,
        project_root: str | Path,
        build_directory: str | Path,
        manifest: Mapping[str, object],
        plan: Mapping[str, object],
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.build_directory = Path(build_directory).resolve()
        raw_items = manifest.get("items", [])
        self.items = [item for item in raw_items if isinstance(item, Mapping)]
        raw_blocks = plan.get("blocks", [])
        self.image_blocks = [
            block
            for block in raw_blocks
            if isinstance(block, Mapping) and block.get("type") == "image"
        ]

    def _item_for_source(self, source: str) -> Mapping[str, object] | None:
        normalized = source.replace("\\", "/")
        for item in self.items:
            if item.get("kind") != "image":
                continue
            candidates = {
                str(item.get("id", "")),
                str(item.get("path", "")),
                str(item.get("original_name", "")),
                Path(str(item.get("path", ""))).name,
            }
            if normalized in candidates:
                return item
        return None

    def _plan_block(
        self, index: int, material_id: str | None = None
    ) -> Mapping[str, object] | None:
        if material_id:
            for block in self.image_blocks:
                if block.get("material_id") == material_id:
                    return block
        if 0 < index <= len(self.image_blocks):
            return self.image_blocks[index - 1]
        return None

    @staticmethod
    def _anchor(block: Mapping[str, object] | None) -> tuple[str | None, str | None]:
        if not block:
            return None, None
        placement = block.get("placement")
        if not isinstance(placement, Mapping):
            return None, None
        for relation in ("before", "after", "inside"):
            target = placement.get(relation)
            if isinstance(target, str):
                return target, relation
        return None, None

    def __call__(
        self,
        source: str,
        alt: str,
        title: str | None,
        index: int,
    ) -> ResolvedImage:
        parsed = urlparse(html.unescape(source.strip()))
        if parsed.scheme in {"http", "https"}:
            block = self._plan_block(index)
            image_id = str(block.get("id")) if block else f"IMG-{index:03d}"
            anchor, relation = self._anchor(block)
            caption = str(block.get("caption") or title or alt) if block else (title or alt)
            filename = _url_filename(source, index)
            trusted = parsed.scheme == "https" and _is_wechat_image_host(parsed.hostname)
            return ResolvedImage(
                image_id=image_id,
                source=html.unescape(source.strip()),
                rendered_src=safe_web_url(source),
                alt=alt,
                caption=caption,
                original_name=filename,
                fallback_text="" if trusted else _fallback_text(image_id, filename, caption),
                fallback_required=not trusted,
                copy_mode="preserve_image",
                delivery_status="ready" if trusted else "awaiting_user_validation",
                fallback="none" if trusted else "manual_upload",
                anchor=anchor,
                anchor_relation=relation,
            )
        if parsed.scheme:
            raise RenderError(
                f"Unsupported image URL scheme: {source}",
                context={"source": source, "scheme": parsed.scheme},
            )

        item = self._item_for_source(source)
        if item is None:
            raise MaterialNotFoundError(
                f"Local image is not registered in the material manifest: {source}",
                context={"source": source},
            )
        relative_path = str(item["path"])
        local_path = safe_join(self.project_root, relative_path)
        if not local_path.is_file():
            raise MaterialNotFoundError(
                f"Registered image file is missing: {relative_path}",
                context={"material_id": item.get("id"), "path": relative_path},
            )
        block = self._plan_block(index, str(item.get("id")))
        image_id = str(block.get("id")) if block else str(item["id"])
        anchor, relation = self._anchor(block)
        caption = str(block.get("caption") or title or alt) if block else (title or alt)
        filename = str(item.get("original_name") or local_path.name)
        asset_name = Path(relative_path).name
        asset_relative = f"assets/images/{asset_name}"
        asset_path = safe_join(self.build_directory, asset_relative)
        atomic_write_bytes(asset_path, local_path.read_bytes())
        return ResolvedImage(
            image_id=image_id,
            source=relative_path,
            rendered_src=html.escape(asset_relative, quote=True),
            alt=alt,
            caption=caption,
            original_name=filename,
            fallback_text=_fallback_text(image_id, filename, caption),
            fallback_required=True,
            copy_mode="preserve_image",
            delivery_status="awaiting_user_validation",
            fallback="manual_upload",
            anchor=anchor,
            anchor_relation=relation,
        )


def image_report_record(image: ResolvedImage) -> dict[str, object]:
    record: dict[str, object] = {
        "id": image.image_id,
        "source": image.source,
        "copy_mode": image.copy_mode,
        "delivery_status": image.delivery_status,
        "fallback": image.fallback,
        "caption": image.caption,
    }
    if image.anchor:
        record["anchor"] = image.anchor
    return record


def render_image_checklist(images: tuple[ResolvedImage, ...]) -> str:
    lines = [
        "# 图片交付清单",
        "",
        "默认先使用预览页的“复制完整图文”按钮。只有图片粘贴失败时，再按本清单手动上传。",
        "",
    ]
    if not images:
        lines.append("本文没有图片。")
        return "\n".join(lines) + "\n"

    for image in images:
        anchor = "未指定"
        if image.anchor:
            relation = {
                "before": "之前",
                "after": "之后",
                "inside": "内部",
            }.get(image.anchor_relation or "", image.anchor_relation or "")
            anchor = f"{image.anchor} {relation}".strip()
        lines.extend(
            [
                f"## {image.image_id}｜{image.original_name}",
                "",
                f"- 图注：{image.caption or '无'}",
                f"- 位置：{anchor}",
                f"- 主复制：{image.copy_mode}",
                f"- 当前状态：{image.delivery_status}",
                f"- 失败兜底：{image.fallback}",
            ]
        )
        if image.fallback_text:
            lines.append(f"- 占位符：{image.fallback_text}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
