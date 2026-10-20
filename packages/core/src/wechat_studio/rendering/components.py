"""Load and fill versioned inline-style HTML components."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from wechat_studio.errors import RenderError
from wechat_studio.storage.paths import resolve_resource_root


COMPONENT_NAMES = (
    "paragraph",
    "section_title",
    "sub_title",
    "key_sentence",
    "quote",
    "image",
    "caption",
    "divider",
    "code",
    "list",
    "lead",
    "ending",
)

PLACEHOLDER_RE = re.compile(r"\{\{[a-z_]+\}\}")


@dataclass(frozen=True, slots=True)
class ComponentCatalog:
    directory: Path
    templates: dict[str, str]

    @classmethod
    def load(cls, directory: str | Path | None = None) -> "ComponentCatalog":
        resolved = (
            Path(directory).resolve()
            if directory is not None
            else resolve_resource_root() / "components" / "base-v1"
        )
        templates: dict[str, str] = {}
        missing: list[str] = []
        for name in COMPONENT_NAMES:
            path = resolved / f"{name}.html"
            if not path.is_file():
                missing.append(path.name)
                continue
            templates[name] = path.read_text(encoding="utf-8").strip()
        if missing:
            raise RenderError(
                f"Component catalog is incomplete: {resolved}",
                context={"directory": str(resolved), "missing": missing},
            )
        return cls(directory=resolved, templates=templates)

    def get(self, name: str) -> str:
        try:
            return self.templates[name]
        except KeyError as exc:
            raise RenderError(
                f"Unknown rendering component: {name}",
                context={"component": name, "directory": str(self.directory)},
            ) from exc

    def fill(self, name: str, **values: str) -> str:
        output = self.get(name)
        for key, value in values.items():
            output = output.replace("{{" + key + "}}", value)
        unresolved = PLACEHOLDER_RE.findall(output)
        if unresolved:
            raise RenderError(
                f"Unresolved placeholders in component {name}.",
                context={"component": name, "placeholders": unresolved},
            )
        return output
