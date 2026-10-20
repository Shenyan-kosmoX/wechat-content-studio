from __future__ import annotations

from pathlib import Path

import pytest

from wechat_studio.errors import UnsafePathError
from wechat_studio.storage.paths import (
    WORKSPACE_ENV,
    resolve_user_data_root,
    resolve_workspace_paths,
    safe_join,
)


def test_explicit_workspace_has_highest_priority(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit"
    result = resolve_user_data_root(
        explicit,
        environ={WORKSPACE_ENV: str(tmp_path / "environment")},
        documents_dir=tmp_path / "Documents",
    )
    assert result == explicit.resolve()


def test_environment_workspace_precedes_documents(tmp_path: Path) -> None:
    configured = tmp_path / "configured"
    result = resolve_user_data_root(
        environ={WORKSPACE_ENV: str(configured)},
        documents_dir=tmp_path / "Documents",
    )
    assert result == configured.resolve()


def test_documents_default_uses_product_folder(tmp_path: Path) -> None:
    documents = tmp_path / "Documents"
    result = resolve_user_data_root(environ={}, documents_dir=documents)
    assert result == (documents / "WeChat Content Studio").resolve()


@pytest.mark.parametrize(
    "unsafe",
    [
        "../secret.txt",
        "materials/../../secret.txt",
        "/absolute/file.txt",
        "C:/absolute/file.txt",
        "C:\\absolute\\file.txt",
        "materials\\image.png",
        "materials//image.png",
        "./article.md",
        "",
    ],
)
def test_safe_join_rejects_nonportable_or_escaping_paths(
    tmp_path: Path, unsafe: str
) -> None:
    with pytest.raises(UnsafePathError):
        safe_join(tmp_path, unsafe)


def test_safe_join_accepts_portable_relative_path(tmp_path: Path) -> None:
    result = safe_join(tmp_path, "materials/images/cover.png")
    assert result == (tmp_path / "materials" / "images" / "cover.png").resolve()


def test_workspace_initialization_creates_user_and_state_layout(tmp_path: Path) -> None:
    paths = resolve_workspace_paths(
        tmp_path / "user",
        state_root=tmp_path / "state",
        resources_root=Path(__file__).parents[2] / "resources",
    ).initialize()

    expected = (
        paths.private_styles,
        paths.imported_styles,
        paths.writing_profiles,
        paths.presets,
        paths.articles,
        paths.cache,
        paths.logs,
        paths.locks,
        paths.temp,
    )
    assert all(path.is_dir() for path in expected)
