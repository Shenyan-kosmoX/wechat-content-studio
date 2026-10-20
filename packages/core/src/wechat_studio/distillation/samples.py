"""Register, deduplicate, persist, and analyze style-reference samples."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from wechat_studio.composition.ids import next_sequence_id, slugify
from wechat_studio.composition.locks import exclusive_lock
from wechat_studio.contracts import is_safe_relative_path
from wechat_studio.errors import (
    SampleConflictError,
    SampleInvalidError,
    SampleNotFoundError,
)
from wechat_studio.storage.atomic import atomic_write_text
from wechat_studio.storage.yaml_io import read_json, read_yaml, write_json_atomic, write_yaml_atomic


SAMPLE_ID_RE = re.compile(r"^SAMPLE-[0-9]{3,}$")
SAMPLE_KINDS = {"url", "html", "text"}
ACCESSIBILITY_STATES = {"unverified", "accessible", "unavailable", "missing"}
ANALYSIS_STATES = {"pending", "ready", "unavailable", "failed"}
EVIDENCE_SCOPES = {"none", "writing_only", "layout_only", "writing_and_layout"}
ARTICLE_TYPES = {"opinion", "tutorial", "review", "news", "interview", "essay", "other"}
TRACKING_QUERY_KEYS = {
    "clicktime",
    "enterid",
    "from",
    "scene",
    "sessionid",
    "share_token",
    "subscene",
}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def canonicalize_url(value: str) -> str:
    """Normalize a public HTTP(S) URL for duplicate detection."""

    raw = value.strip()
    parts = urlsplit(raw)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise SampleInvalidError(
            f"Sample URL must be an absolute HTTP(S) URL: {value}",
            context={"url": value},
        )
    if parts.username or parts.password:
        raise SampleInvalidError(
            "Sample URLs must not contain credentials.",
            context={"url": value},
        )

    scheme = parts.scheme.lower()
    hostname = parts.hostname.encode("idna").decode("ascii").lower()
    if hostname == "mp.weixin.qq.com":
        scheme = "https"
    port = parts.port
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        netloc = f"{hostname}:{port}"
    else:
        netloc = hostname

    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_KEYS
    ]
    query.sort()
    return urlunsplit((scheme, netloc, path, urlencode(query, doseq=True), ""))


def _normalized_content(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _content_digest(value: str) -> str:
    return hashlib.sha256(_normalized_content(value).encode("utf-8")).hexdigest()


def _decode_bytes(value: bytes, source: Path) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise SampleInvalidError(
        f"Sample text encoding is not supported: {source}",
        context={"path": str(source), "supported_encodings": ["utf-8", "gb18030"]},
    )


@dataclass(frozen=True, slots=True)
class SampleImportResult:
    record: dict[str, Any]
    created: bool
    duplicate_of: str | None = None


class SampleRegistry:
    """A small, lock-protected evidence collection rooted at one directory."""

    def __init__(
        self,
        root: str | Path,
        *,
        collection_id: str | None = None,
        lock_path: str | Path | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.collection_id = collection_id or slugify(self.root.name, fallback="samples")
        self.manifest_path = self.root / "samples.yaml"
        self.content_directory = self.root / "content"
        self.analysis_directory = self.root / "analysis"
        self.lock_path = Path(lock_path).resolve() if lock_path else self.root / ".samples.lock"

    def initialize(self) -> "SampleRegistry":
        self.content_directory.mkdir(parents=True, exist_ok=True)
        self.analysis_directory.mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.exists():
            timestamp = _now()
            self._write(
                {
                    "sample_manifest_schema_version": "1.0",
                    "collection_id": self.collection_id,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "samples": [],
                }
            )
        else:
            self.load()
        return self

    def load(self) -> dict[str, Any]:
        if not self.manifest_path.is_file():
            raise SampleNotFoundError(
                f"Sample collection does not exist: {self.root}",
                context={"path": str(self.root)},
            )
        document = read_yaml(self.manifest_path)
        self._validate(document)
        return document

    def list(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.load()["samples"]]

    def get(self, sample_id: str) -> dict[str, Any]:
        for item in self.load()["samples"]:
            if item["sample_id"] == sample_id:
                return dict(item)
        raise SampleNotFoundError(
            f"Sample not found: {sample_id}",
            context={"sample_id": sample_id, "collection": str(self.root)},
        )

    def register_url(
        self,
        url: str,
        *,
        title: str = "",
        article_type: str = "other",
        accessibility: str = "unverified",
        confirmed_by_user: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> SampleImportResult:
        canonical = canonicalize_url(url)
        self._check_common(article_type=article_type, accessibility=accessibility)
        self.initialize()
        with exclusive_lock(self.lock_path, timeout_seconds=2.0):
            document = self.load()
            duplicate = self._by_canonical_url(document, canonical)
            if duplicate is not None:
                return SampleImportResult(dict(duplicate), False, duplicate["sample_id"])
            timestamp = _now()
            record = self._new_record(
                document,
                kind="url",
                title=title,
                article_type=article_type,
                accessibility=accessibility,
                confirmed_by_user=confirmed_by_user,
                source_url=url,
                canonical_url=canonical,
                metadata=metadata,
                timestamp=timestamp,
            )
            document["samples"].append(record)
            document["updated_at"] = timestamp
            self._write(document)
            return SampleImportResult(dict(record), True)

    def import_path(
        self,
        source: str | Path,
        *,
        kind: str | None = None,
        source_url: str | None = None,
        title: str = "",
        article_type: str = "other",
        confirmed_by_user: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> SampleImportResult:
        path = Path(source).resolve()
        if not path.is_file():
            raise SampleNotFoundError(
                f"Sample file does not exist: {path}",
                context={"path": str(path), "accessibility": "missing"},
            )
        text = _decode_bytes(path.read_bytes(), path)
        detected = kind or ("html" if path.suffix.lower() in {".html", ".htm"} else "text")
        return self.import_content(
            text,
            kind=detected,
            source_url=source_url,
            title=title or path.stem,
            article_type=article_type,
            confirmed_by_user=confirmed_by_user,
            metadata={**dict(metadata or {}), "original_filename": path.name},
        )

    def import_content(
        self,
        content: str,
        *,
        kind: str,
        source_url: str | None = None,
        title: str = "",
        article_type: str = "other",
        confirmed_by_user: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> SampleImportResult:
        if kind not in {"html", "text"}:
            raise SampleInvalidError(
                "Imported content kind must be html or text.",
                context={"kind": kind},
            )
        if not isinstance(content, str) or not content.strip():
            raise SampleInvalidError("Sample content cannot be empty.")
        self._check_common(article_type=article_type, accessibility="accessible")
        canonical = canonicalize_url(source_url) if source_url else None
        normalized = _normalized_content(content)
        digest = _content_digest(normalized)
        self.initialize()

        with exclusive_lock(self.lock_path, timeout_seconds=2.0):
            document = self.load()
            url_match = self._by_canonical_url(document, canonical) if canonical else None
            hash_match = self._by_digest(document, digest)
            if hash_match is not None and hash_match is not url_match:
                return SampleImportResult(dict(hash_match), False, hash_match["sample_id"])
            if url_match is not None and url_match.get("content_sha256"):
                if url_match["content_sha256"] == digest:
                    return SampleImportResult(dict(url_match), False, url_match["sample_id"])
                raise SampleConflictError(
                    "The same canonical URL was registered with different content.",
                    context={
                        "sample_id": url_match["sample_id"],
                        "canonical_url": canonical,
                        "existing_sha256": url_match["content_sha256"],
                        "incoming_sha256": digest,
                    },
                )

            timestamp = _now()
            if url_match is not None:
                record = url_match
                record["accessibility"] = "accessible"
                record["confirmed_by_user"] = bool(
                    record["confirmed_by_user"] or confirmed_by_user
                )
                record["title"] = title or record["title"]
                record["article_type"] = article_type
                record["metadata"].update(dict(metadata or {}))
                record["updated_at"] = timestamp
                created = False
            else:
                record = self._new_record(
                    document,
                    kind=kind,
                    title=title,
                    article_type=article_type,
                    accessibility="accessible",
                    confirmed_by_user=confirmed_by_user,
                    source_url=source_url,
                    canonical_url=canonical,
                    metadata=metadata,
                    timestamp=timestamp,
                )
                document["samples"].append(record)
                created = True

            extension = ".html" if kind == "html" else ".txt"
            relative_path = f"content/{record['sample_id']}{extension}"
            atomic_write_text(self.root / relative_path, normalized)
            record["payload_kind"] = kind
            record["content_path"] = relative_path
            record["content_sha256"] = digest
            record["content_media_type"] = "text/html" if kind == "html" else "text/plain"
            record["analysis_status"] = "pending"
            record["analysis_path"] = None
            record["evidence_scope"] = "none"
            document["updated_at"] = timestamp
            self._write(document)
            return SampleImportResult(dict(record), created)

    def analyze(self, sample_id: str) -> dict[str, Any]:
        """Analyze one locally available payload and persist the evidence report."""

        self.initialize()
        with exclusive_lock(self.lock_path, timeout_seconds=2.0):
            document = self.load()
            record = next(
                (item for item in document["samples"] if item["sample_id"] == sample_id),
                None,
            )
            if record is None:
                raise SampleNotFoundError(
                    f"Sample not found: {sample_id}",
                    context={"sample_id": sample_id},
                )

            timestamp = _now()
            if not record.get("content_path"):
                report = {
                    "distillation_evidence_version": "1.0",
                    "sample_id": sample_id,
                    "source_kind": record["kind"],
                    "article_type": record["article_type"],
                    "accessibility": record["accessibility"],
                    "evidence_scope": "none",
                    "writing": None,
                    "layout": None,
                    "warnings": ["sample_has_no_local_payload"],
                }
                record["analysis_status"] = "unavailable"
            else:
                payload_path = self.root / record["content_path"]
                if not payload_path.is_file():
                    record["accessibility"] = "missing"
                    record["analysis_status"] = "failed"
                    record["updated_at"] = timestamp
                    document["updated_at"] = timestamp
                    self._write(document)
                    raise SampleNotFoundError(
                        f"Stored sample payload is missing: {payload_path}",
                        context={"sample_id": sample_id, "path": str(payload_path)},
                    )
                payload = payload_path.read_text(encoding="utf-8")
                from .html_evidence import analyze_html_evidence, analyze_text_evidence

                if record["payload_kind"] == "html":
                    report = analyze_html_evidence(
                        sample_id,
                        payload,
                        article_type=record["article_type"],
                        source_kind=record["kind"],
                    )
                else:
                    report = analyze_text_evidence(
                        sample_id,
                        payload,
                        article_type=record["article_type"],
                        source_kind=record["kind"],
                    )
                record["analysis_status"] = "ready"

            relative_path = f"analysis/{sample_id}.json"
            write_json_atomic(self.root / relative_path, report)
            record["analysis_path"] = relative_path
            record["evidence_scope"] = report["evidence_scope"]
            record["updated_at"] = timestamp
            document["updated_at"] = timestamp
            self._write(document)
            return report

    def analyze_all(self, *, confirmed_only: bool = False) -> list[dict[str, Any]]:
        records = self.list()
        return [
            self.analyze(record["sample_id"])
            for record in records
            if not confirmed_only or record["confirmed_by_user"]
        ]

    def load_analysis(self, sample_id: str) -> dict[str, Any]:
        record = self.get(sample_id)
        path = record.get("analysis_path")
        if not path:
            raise SampleNotFoundError(
                f"Sample has no analysis report: {sample_id}",
                context={"sample_id": sample_id},
            )
        return read_json(self.root / path)

    @staticmethod
    def _check_common(*, article_type: str, accessibility: str) -> None:
        if article_type not in ARTICLE_TYPES:
            raise SampleInvalidError(
                f"Unsupported article type: {article_type}",
                context={"article_type": article_type, "supported": sorted(ARTICLE_TYPES)},
            )
        if accessibility not in ACCESSIBILITY_STATES:
            raise SampleInvalidError(
                f"Unsupported accessibility state: {accessibility}",
                context={"accessibility": accessibility},
            )

    @staticmethod
    def _by_canonical_url(document: dict[str, Any], canonical: str | None) -> dict[str, Any] | None:
        if canonical is None:
            return None
        return next(
            (item for item in document["samples"] if item.get("canonical_url") == canonical),
            None,
        )

    @staticmethod
    def _by_digest(document: dict[str, Any], digest: str) -> dict[str, Any] | None:
        return next(
            (item for item in document["samples"] if item.get("content_sha256") == digest),
            None,
        )

    def _new_record(
        self,
        document: dict[str, Any],
        *,
        kind: str,
        title: str,
        article_type: str,
        accessibility: str,
        confirmed_by_user: bool,
        source_url: str | None,
        canonical_url: str | None,
        metadata: Mapping[str, Any] | None,
        timestamp: str,
    ) -> dict[str, Any]:
        return {
            "sample_id": next_sequence_id(
                "SAMPLE", {item["sample_id"] for item in document["samples"]}
            ),
            "kind": kind,
            "payload_kind": None,
            "title": title.strip(),
            "article_type": article_type,
            "accessibility": accessibility,
            "confirmed_by_user": bool(confirmed_by_user),
            "source_url": source_url,
            "canonical_url": canonical_url,
            "content_path": None,
            "content_sha256": None,
            "content_media_type": None,
            "analysis_status": "pending" if accessibility != "unavailable" else "unavailable",
            "analysis_path": None,
            "evidence_scope": "none",
            "created_at": timestamp,
            "updated_at": timestamp,
            "metadata": dict(metadata or {}),
        }

    def _write(self, document: dict[str, Any]) -> None:
        write_yaml_atomic(self.manifest_path, document, validator=self._validate)

    def _validate(self, document: Any) -> None:
        if not isinstance(document, dict):
            raise SampleInvalidError("Sample manifest root must be an object.")
        required = {
            "sample_manifest_schema_version",
            "collection_id",
            "created_at",
            "updated_at",
            "samples",
        }
        if set(document) != required:
            raise SampleInvalidError(
                "Sample manifest has missing or unknown fields.",
                context={
                    "missing": sorted(required - set(document)),
                    "unknown": sorted(set(document) - required),
                },
            )
        if document["sample_manifest_schema_version"] != "1.0":
            raise SampleInvalidError(
                "Unsupported sample manifest schema version.",
                context={"actual": document["sample_manifest_schema_version"]},
            )
        if not isinstance(document["samples"], list):
            raise SampleInvalidError("samples must be a list.")

        ids: set[str] = set()
        urls: set[str] = set()
        hashes: set[str] = set()
        paths: set[str] = set()
        required_record = {
            "sample_id",
            "kind",
            "payload_kind",
            "title",
            "article_type",
            "accessibility",
            "confirmed_by_user",
            "source_url",
            "canonical_url",
            "content_path",
            "content_sha256",
            "content_media_type",
            "analysis_status",
            "analysis_path",
            "evidence_scope",
            "created_at",
            "updated_at",
            "metadata",
        }
        for index, item in enumerate(document["samples"]):
            if not isinstance(item, dict) or set(item) != required_record:
                raise SampleInvalidError(
                    "Sample record has missing or unknown fields.",
                    context={"index": index},
                )
            sample_id = item["sample_id"]
            if not isinstance(sample_id, str) or not SAMPLE_ID_RE.fullmatch(sample_id):
                raise SampleInvalidError("Invalid sample ID.", context={"sample_id": sample_id})
            if sample_id in ids:
                raise SampleConflictError("Duplicate sample ID.", context={"sample_id": sample_id})
            ids.add(sample_id)
            if item["kind"] not in SAMPLE_KINDS or item["payload_kind"] not in {None, "html", "text"}:
                raise SampleInvalidError("Invalid sample kind.", context={"sample_id": sample_id})
            self._check_common(
                article_type=item["article_type"], accessibility=item["accessibility"]
            )
            if item["analysis_status"] not in ANALYSIS_STATES:
                raise SampleInvalidError("Invalid analysis status.", context={"sample_id": sample_id})
            if item["evidence_scope"] not in EVIDENCE_SCOPES:
                raise SampleInvalidError("Invalid evidence scope.", context={"sample_id": sample_id})
            for field in ("content_path", "analysis_path"):
                value = item[field]
                if value is not None and not is_safe_relative_path(value):
                    raise SampleInvalidError(
                        "Sample record contains an unsafe path.",
                        context={"sample_id": sample_id, "field": field, "path": value},
                    )
                if value is not None and field == "content_path":
                    if value in paths:
                        raise SampleConflictError(
                            "Multiple samples point to the same content path.",
                            context={"path": value},
                        )
                    paths.add(value)
            canonical = item["canonical_url"]
            if canonical is not None:
                if canonical in urls:
                    raise SampleConflictError(
                        "Duplicate canonical sample URL.", context={"canonical_url": canonical}
                    )
                urls.add(canonical)
            digest = item["content_sha256"]
            if digest is not None:
                if not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise SampleInvalidError(
                        "Invalid sample content digest.", context={"sample_id": sample_id}
                    )
                if digest in hashes:
                    raise SampleConflictError(
                        "Duplicate sample content digest.", context={"sha256": digest}
                    )
                hashes.add(digest)
