"""Archive user-owned Style Packs without deleting historical versions."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from wechat_studio.contracts import ContractValidator
from wechat_studio.errors import StyleImmutableError
from wechat_studio.storage.yaml_io import read_yaml, write_yaml_atomic

from .pack import StylePack


def archive_style_pack(pack: StylePack | str | Path) -> StylePack:
    style = pack if isinstance(pack, StylePack) else StylePack.load(pack)
    if style.layer == "builtin":
        raise StyleImmutableError(
            "Built-in Style Packs are read-only and cannot be archived in place.",
            context={"path": str(style.root)},
        )
    validator = ContractValidator()
    style_path = style.root / "style.yaml"
    document = read_yaml(style_path)
    document["status"] = "archived"
    extensions = document.setdefault("extensions", {})
    archive = extensions.setdefault("shenyan.archive", {})
    archive["archived_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    write_yaml_atomic(
        style_path,
        document,
        validator=lambda value: validator.validate_or_raise(value, "style-pack"),
    )
    return StylePack.load(style.root, expected_layer=style.layer)
