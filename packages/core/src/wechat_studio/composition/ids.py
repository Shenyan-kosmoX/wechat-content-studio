"""Generate portable and stable project and sequence identifiers."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from uuid import uuid4


PROJECT_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
SEQUENCE_ID_RE = re.compile(r"^(?P<prefix>[A-Z]+)-(?P<number>[0-9]{3,})$")


def slugify(value: str, *, fallback: str = "article", max_length: int = 48) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    slug = slug or fallback
    return slug[:max_length].rstrip("-") or fallback


def make_project_id(name: str, *, now: datetime | None = None, suffix: str | None = None) -> str:
    moment = now or datetime.now().astimezone()
    token = (suffix or uuid4().hex[:6]).lower()
    base = slugify(name, max_length=40)
    project_id = f"{base}-{moment:%Y%m%d}-{token}"
    if not PROJECT_ID_RE.fullmatch(project_id):  # pragma: no cover - defensive guard
        raise ValueError(f"Generated invalid project id: {project_id}")
    return project_id


def next_sequence_id(prefix: str, existing_ids: list[str] | tuple[str, ...] | set[str]) -> str:
    normalized = prefix.upper()
    highest = 0
    for value in existing_ids:
        match = SEQUENCE_ID_RE.fullmatch(value)
        if match and match.group("prefix") == normalized:
            highest = max(highest, int(match.group("number")))
    return f"{normalized}-{highest + 1:03d}"
