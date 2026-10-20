"""Strict semantic-version parsing and deterministic style directory names."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import total_ordering

from wechat_studio.errors import StyleInvalidError


SEMVER_PATTERN = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?$"
)


@total_ordering
@dataclass(frozen=True, slots=True)
class SemanticVersion:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()

    @property
    def stable(self) -> bool:
        return not self.prerelease

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return base if self.stable else base + "-" + ".".join(self.prerelease)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        core = (self.major, self.minor, self.patch)
        other_core = (other.major, other.minor, other.patch)
        if core != other_core:
            return core < other_core
        if self.stable != other.stable:
            return not self.stable
        return _compare_prerelease(self.prerelease, other.prerelease) < 0


def _compare_prerelease(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    for a, b in zip(left, right):
        if a == b:
            continue
        a_numeric = a.isdigit()
        b_numeric = b.isdigit()
        if a_numeric and b_numeric:
            return -1 if int(a) < int(b) else 1
        if a_numeric != b_numeric:
            return -1 if a_numeric else 1
        return -1 if a < b else 1
    if len(left) == len(right):
        return 0
    return -1 if len(left) < len(right) else 1


def parse_semver(value: str) -> SemanticVersion:
    match = SEMVER_PATTERN.fullmatch(value)
    if not match:
        raise StyleInvalidError(
            f"Invalid semantic version: {value}",
            context={"version": value},
        )
    prerelease = tuple((match.group("prerelease") or "").split("."))
    if prerelease == ("",):
        prerelease = ()
    return SemanticVersion(
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        prerelease,
    )


def stable_version(value: str) -> str:
    parsed = parse_semver(value)
    return f"{parsed.major}.{parsed.minor}.{parsed.patch}"


def style_directory_name(style_id: str, version: str) -> str:
    parse_semver(version)
    return f"{style_id}-v{version}"
