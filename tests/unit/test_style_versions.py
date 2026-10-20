from __future__ import annotations

import pytest

from wechat_studio.errors import StyleInvalidError
from wechat_studio.styles import parse_semver, style_directory_name


def test_semantic_versions_sort_prerelease_before_stable() -> None:
    versions = [
        parse_semver("1.1.0"),
        parse_semver("1.0.0"),
        parse_semver("1.1.0-candidate.2"),
        parse_semver("1.1.0-candidate.10"),
    ]

    assert [str(item) for item in sorted(versions)] == [
        "1.0.0",
        "1.1.0-candidate.2",
        "1.1.0-candidate.10",
        "1.1.0",
    ]


def test_style_directory_name_is_version_pinned() -> None:
    assert style_directory_name("basic-editorial", "1.0.0") == "basic-editorial-v1.0.0"


@pytest.mark.parametrize("invalid", ["1", "v1.0.0", "1.0", "01.0.0", "1.0.0-"])
def test_invalid_semantic_version_is_rejected(invalid: str) -> None:
    with pytest.raises(StyleInvalidError):
        parse_semver(invalid)
