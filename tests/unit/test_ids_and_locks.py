from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from wechat_studio.composition.ids import make_project_id, next_sequence_id, slugify
from wechat_studio.composition.locks import exclusive_lock
from wechat_studio.errors import LockBusyError


def test_slugify_and_project_id_are_portable() -> None:
    assert slugify("Hello, WeChat Studio!") == "hello-wechat-studio"
    assert slugify("微信公众号文章") == "article"
    assert (
        make_project_id(
            "Product Review",
            now=datetime(2026, 8, 12, tzinfo=timezone.utc),
            suffix="abc123",
        )
        == "product-review-20260812-abc123"
    )


def test_next_sequence_id_ignores_other_prefixes() -> None:
    assert next_sequence_id("IMG", {"IMG-001", "IMG-009", "TEXT-100"}) == "IMG-010"


def test_exclusive_lock_rejects_second_holder(tmp_path: Path) -> None:
    lock = tmp_path / "project.lock"
    with exclusive_lock(lock):
        with pytest.raises(LockBusyError):
            with exclusive_lock(lock):
                pass
    assert not lock.exists()
