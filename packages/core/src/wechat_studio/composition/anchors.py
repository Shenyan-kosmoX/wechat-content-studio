"""Validate material references, anchor targets, and locked plan edits."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from wechat_studio.errors import AnchorConflictError, LockConflictError, MaterialNotFoundError


def _blocks_by_id(plan: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    blocks = plan.get("blocks", [])
    return {
        block["id"]: block
        for block in blocks
        if isinstance(block, Mapping) and isinstance(block.get("id"), str)
    }


def _materials_by_id(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    items = manifest.get("items", [])
    return {
        item["id"]: item
        for item in items
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }


def validate_plan_references(plan: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
    blocks = _blocks_by_id(plan)
    materials = _materials_by_id(manifest)
    for block_id, block in blocks.items():
        content_ref = block.get("content_ref")
        if isinstance(content_ref, str):
            item = materials.get(content_ref)
            if item is None or item.get("kind") not in {"text", "reference"}:
                raise MaterialNotFoundError(
                    f"Article block {block_id} references missing text material {content_ref}.",
                    context={"block_id": block_id, "material_id": content_ref},
                )
        material_id = block.get("material_id")
        if isinstance(material_id, str):
            item = materials.get(material_id)
            if item is None or item.get("kind") != "image":
                raise MaterialNotFoundError(
                    f"Image block {block_id} references missing image material {material_id}.",
                    context={"block_id": block_id, "material_id": material_id},
                )
        placement = block.get("placement")
        if not isinstance(placement, Mapping):
            continue
        for relation in ("before", "after", "inside"):
            target = placement.get(relation)
            if not isinstance(target, str):
                continue
            if target not in blocks:
                raise AnchorConflictError(
                    f"Anchor target {target} for {block_id} does not exist.",
                    context={"block_id": block_id, "relation": relation, "target": target},
                )
            if target == block_id:
                raise AnchorConflictError(
                    f"Article block {block_id} cannot anchor to itself.",
                    context={"block_id": block_id, "relation": relation},
                )


def assert_locked_constraints_preserved(
    previous: Mapping[str, Any], candidate: Mapping[str, Any]
) -> None:
    previous_blocks = _blocks_by_id(previous)
    candidate_blocks = _blocks_by_id(candidate)

    for block_id, old_block in previous_blocks.items():
        new_block = candidate_blocks.get(block_id)
        if old_block.get("locked") is True:
            if new_block is None:
                raise LockConflictError(
                    f"Locked block {block_id} cannot be removed.",
                    context={"block_id": block_id, "change": "removed"},
                )
            if dict(new_block) != dict(old_block):
                raise LockConflictError(
                    f"Locked block {block_id} cannot be changed.",
                    context={"block_id": block_id, "change": "modified"},
                )

        old_placement = old_block.get("placement")
        if isinstance(old_placement, Mapping) and old_placement.get("locked") is True:
            if new_block is None or new_block.get("placement") != old_placement:
                raise LockConflictError(
                    f"Locked placement for {block_id} cannot be changed.",
                    context={"block_id": block_id, "change": "placement"},
                )

    old_locked_order = [
        block_id
        for block_id, block in previous_blocks.items()
        if block.get("locked") is True
        or (isinstance(block.get("placement"), Mapping) and block["placement"].get("locked") is True)
    ]
    candidate_order = [
        block.get("id")
        for block in candidate.get("blocks", [])
        if isinstance(block, Mapping) and block.get("id") in old_locked_order
    ]
    if candidate_order != old_locked_order:
        raise LockConflictError(
            "The relative order of locked blocks cannot change.",
            context={"expected": old_locked_order, "actual": candidate_order},
        )
