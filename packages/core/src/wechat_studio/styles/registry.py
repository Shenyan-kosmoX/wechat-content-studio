"""Discover Style Packs across project, private, built-in, and import roots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from wechat_studio.errors import StyleConflictError
from wechat_studio.storage.paths import WorkspacePaths

from .pack import StylePack
from .versions import parse_semver


LAYER_PRECEDENCE = ("project", "private", "builtin")


@dataclass(slots=True)
class StyleRegistry:
    paths: WorkspacePaths
    project_root: Path | None = None

    def roots(self) -> dict[str, Path]:
        roots = {
            "private": self.paths.private_styles,
            "builtin": self.paths.resources_root / "builtin-styles",
        }
        if self.project_root is not None:
            roots["project"] = self.project_root.resolve() / "styles" / "local"
        return roots

    @staticmethod
    def _directories(root: Path) -> list[Path]:
        if not root.is_dir():
            return []
        return sorted(
            path
            for path in root.iterdir()
            if path.is_dir() and not path.name.startswith(".") and (path / "style.yaml").is_file()
        )

    def discover(
        self,
        *,
        include_archived: bool = False,
        include_candidates: bool = False,
    ) -> list[StylePack]:
        packs: list[StylePack] = []
        seen: dict[tuple[str, str, str], Path] = {}
        roots = self.roots()
        for layer in LAYER_PRECEDENCE:
            root = roots.get(layer)
            if root is None:
                continue
            for directory in self._directories(root):
                pack = StylePack.load(
                    directory,
                    expected_layer=layer,
                    require_directory_name=True,
                )
                if pack.status == "archived" and not include_archived:
                    continue
                if pack.status == "candidate" and not include_candidates:
                    continue
                previous = seen.get(pack.key)
                if previous is not None:
                    raise StyleConflictError(
                        f"Duplicate Style Pack version: {pack.style_id} {pack.version}",
                        context={
                            "key": list(pack.key),
                            "first": str(previous),
                            "second": str(directory),
                        },
                    )
                seen[pack.key] = directory
                packs.append(pack)
        return sorted(
            packs,
            key=lambda pack: (
                LAYER_PRECEDENCE.index(pack.layer),
                pack.style_id,
                parse_semver(pack.version),
            ),
        )

    def discover_imports(self) -> list[StylePack]:
        packs: list[StylePack] = []
        for directory in self._directories(self.paths.imported_styles):
            pack = StylePack.load(directory, require_directory_name=True)
            if pack.status != "candidate":
                continue
            packs.append(pack)
        return sorted(packs, key=lambda pack: (pack.style_id, parse_semver(pack.version)))

    def list_records(
        self,
        *,
        include_archived: bool = False,
        include_candidates: bool = False,
        include_imports: bool = False,
    ) -> list[dict[str, object]]:
        packs = self.discover(
            include_archived=include_archived,
            include_candidates=include_candidates,
        )
        if include_imports:
            packs.extend(self.discover_imports())
        return [pack.to_record() for pack in packs]
