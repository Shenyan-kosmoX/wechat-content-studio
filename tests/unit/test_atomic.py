from __future__ import annotations

from pathlib import Path

import pytest

from wechat_studio.errors import AtomicWriteError
from wechat_studio.storage.atomic import atomic_replace_directory, atomic_write_text
from wechat_studio.storage.yaml_io import read_json, read_yaml, write_json_atomic, write_yaml_atomic


def test_atomic_write_replaces_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "value.txt"
    target.write_text("old", encoding="utf-8")

    atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "new"


def test_atomic_write_validation_failure_preserves_old_file(tmp_path: Path) -> None:
    target = tmp_path / "value.txt"
    target.write_text("old", encoding="utf-8")

    def reject(_: Path) -> None:
        raise ValueError("rejected")

    with pytest.raises(AtomicWriteError):
        atomic_write_text(target, "new", validator=reject)

    assert target.read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".value.txt.*.tmp"))


def test_yaml_round_trip_is_utf8_and_ordered(tmp_path: Path) -> None:
    target = tmp_path / "document.yaml"
    document = {"title": "中文标题", "items": ["一", "二"]}

    write_yaml_atomic(target, document)

    assert read_yaml(target) == document
    assert target.read_bytes().startswith(b"title:")


def test_json_validator_failure_preserves_previous_document(tmp_path: Path) -> None:
    target = tmp_path / "document.json"
    write_json_atomic(target, {"version": 1})

    def reject(document: object) -> None:
        if document != {"version": 1}:
            raise ValueError("unsupported")

    with pytest.raises(AtomicWriteError):
        write_json_atomic(target, {"version": 2}, validator=reject)

    assert read_json(target) == {"version": 1}


def test_atomic_directory_replace_rolls_back_when_commit_fails(tmp_path: Path) -> None:
    target = tmp_path / "build"
    target.mkdir()
    (target / "version.txt").write_text("old", encoding="utf-8")
    staged = tmp_path / ".build.next"
    staged.mkdir()
    (staged / "version.txt").write_text("new", encoding="utf-8")

    def fail_commit() -> None:
        raise ValueError("project update failed")

    with pytest.raises(AtomicWriteError):
        atomic_replace_directory(target, staged, after_replace=fail_commit)

    assert (target / "version.txt").read_text(encoding="utf-8") == "old"
    assert not staged.exists()


def test_atomic_directory_replace_commits_new_directory(tmp_path: Path) -> None:
    target = tmp_path / "build"
    target.mkdir()
    (target / "version.txt").write_text("old", encoding="utf-8")
    staged = tmp_path / ".build.next"
    staged.mkdir()
    (staged / "version.txt").write_text("new", encoding="utf-8")

    atomic_replace_directory(target, staged)

    assert (target / "version.txt").read_text(encoding="utf-8") == "new"
    assert not (tmp_path / ".build.backup").exists()
