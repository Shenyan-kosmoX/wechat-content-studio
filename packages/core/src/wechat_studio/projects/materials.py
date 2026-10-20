"""Import immutable source materials and maintain a validated manifest."""

from __future__ import annotations

import hashlib
import mimetypes
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from wechat_studio.composition.ids import next_sequence_id
from wechat_studio.composition.locks import exclusive_lock
from wechat_studio.contracts import ContractValidator
from wechat_studio.errors import MaterialConflictError, MaterialNotFoundError
from wechat_studio.storage.atomic import atomic_write_bytes
from wechat_studio.storage.paths import safe_join
from wechat_studio.storage.yaml_io import read_yaml, write_yaml_atomic


MaterialKind = Literal["text", "reference", "image"]
PREFIX_BY_KIND = {"text": "TEXT", "reference": "REF", "image": "IMG"}
DIRECTORY_BY_KIND = {
    "text": "materials/source-text",
    "reference": "materials/source-text",
    "image": "materials/images",
}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_filename(value: str, *, fallback: str) -> str:
    name = Path(value).name.strip()
    name = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "-", name)
    name = re.sub(r"\s+", "-", name).strip(" .-")
    return (name or fallback)[:180]


class MaterialStore:
    def __init__(
        self,
        project_root: str | Path,
        *,
        project_id: str,
        lock_path: str | Path | None = None,
        validator: ContractValidator | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.project_id = project_id
        self.manifest_path = self.project_root / "materials" / "manifest.yaml"
        self.lock_path = Path(lock_path) if lock_path else self.project_root / ".materials.lock"
        self.validator = validator or ContractValidator()

    def load(self) -> dict[str, Any]:
        document = read_yaml(self.manifest_path)
        self.validator.validate_or_raise(document, "material-manifest")
        if document["project_id"] != self.project_id:
            raise MaterialConflictError(
                "Material manifest belongs to another project.",
                context={
                    "expected_project_id": self.project_id,
                    "actual_project_id": document["project_id"],
                },
            )
        return document

    def _write(self, manifest: dict[str, Any]) -> None:
        manifest["generated_at"] = _now()
        self.validator.validate_or_raise(manifest, "material-manifest")
        write_yaml_atomic(
            self.manifest_path,
            manifest,
            validator=lambda value: self.validator.validate_or_raise(
                value, "material-manifest"
            ),
        )

    def import_file(
        self,
        source: str | Path,
        *,
        kind: MaterialKind,
        summary: str = "",
        locked: bool = True,
        source_kind: str = "user_upload",
        source_reference: str | None = None,
    ) -> dict[str, Any]:
        source_path = Path(source)
        if not source_path.is_file():
            raise MaterialNotFoundError(
                f"Material file does not exist: {source_path}",
                context={"path": str(source_path)},
            )
        return self._import_bytes(
            source_path.read_bytes(),
            original_name=source_path.name,
            kind=kind,
            summary=summary,
            locked=locked,
            source_kind=source_kind,
            source_reference=source_reference or source_path.name,
            mime_type=mimetypes.guess_type(source_path.name)[0],
        )

    def import_text(
        self,
        content: str,
        *,
        original_name: str = "pasted.md",
        kind: Literal["text", "reference"] = "text",
        summary: str = "",
        locked: bool = True,
        source_kind: str = "pasted",
        source_reference: str = "user-pasted-text",
    ) -> dict[str, Any]:
        mime_type = "text/markdown" if original_name.lower().endswith(".md") else "text/plain"
        return self._import_bytes(
            content.encode("utf-8"),
            original_name=original_name,
            kind=kind,
            summary=summary,
            locked=locked,
            source_kind=source_kind,
            source_reference=source_reference,
            mime_type=mime_type,
        )

    def _import_bytes(
        self,
        data: bytes,
        *,
        original_name: str,
        kind: MaterialKind,
        summary: str,
        locked: bool,
        source_kind: str,
        source_reference: str,
        mime_type: str | None,
    ) -> dict[str, Any]:
        if kind not in PREFIX_BY_KIND:
            raise MaterialConflictError(
                f"Unsupported material kind: {kind}",
                context={"kind": kind},
            )
        if kind == "image" and not (mime_type or "").startswith("image/"):
            raise MaterialConflictError(
                f"Image material must have an image MIME type: {original_name}",
                context={"name": original_name, "mime_type": mime_type},
            )
        digest = _sha256(data)
        with exclusive_lock(self.lock_path, timeout_seconds=2.0):
            manifest = self.load()
            for item in manifest["items"]:
                if item["kind"] == kind and item["sha256"] == digest:
                    return item

            material_id = next_sequence_id(
                PREFIX_BY_KIND[kind],
                {item["id"] for item in manifest["items"]},
            )
            clean_name = _safe_filename(original_name, fallback=f"{material_id.lower()}.bin")
            relative_path = f"{DIRECTORY_BY_KIND[kind]}/{material_id}-{clean_name}"
            destination = safe_join(self.project_root, relative_path)
            item: dict[str, Any] = {
                "id": material_id,
                "kind": kind,
                "path": relative_path,
                "original_name": original_name,
                "mime_type": mime_type or "application/octet-stream",
                "sha256": digest,
                "bytes": len(data),
                "summary": summary,
                "source": {"kind": source_kind, "reference": source_reference},
                "integrity": "verified",
                "locked": locked,
            }
            if kind == "image" and not item["mime_type"].startswith("image/"):
                raise MaterialConflictError(
                    f"Image material has invalid MIME type: {item['mime_type']}",
                    context={"id": material_id, "mime_type": item["mime_type"]},
                )

            atomic_write_bytes(destination, data)
            try:
                manifest["items"].append(item)
                self._write(manifest)
            except Exception:
                destination.unlink(missing_ok=True)
                raise
            return item

    def verify(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for item in self.load()["items"]:
            path = safe_join(self.project_root, item["path"])
            if not path.is_file():
                status = "missing"
            elif _sha256(path.read_bytes()) != item["sha256"]:
                status = "mismatch"
            else:
                status = "verified"
            results.append({"id": item["id"], "path": item["path"], "status": status})
        return results
