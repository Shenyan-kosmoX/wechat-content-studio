from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from wechat_studio.contracts import ContractValidator
from wechat_studio_cli.__main__ import main


REPOSITORY = Path(__file__).parents[2]
RESOURCES = REPOSITORY / "resources"
CORE_SRC = REPOSITORY / "packages" / "core" / "src"
CLI_SRC = REPOSITORY / "apps" / "cli" / "src"


def global_args(tmp_path: Path) -> list[str]:
    return [
        "--format",
        "json",
        "--workspace",
        str(tmp_path / "user"),
        "--state-root",
        str(tmp_path / "state"),
        "--resources-root",
        str(RESOURCES),
    ]


def invoke(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    *arguments: str,
    expected_code: int = 0,
) -> dict[str, Any]:
    code = main([*global_args(tmp_path), *arguments])
    captured = capsys.readouterr()
    assert code == expected_code
    if expected_code == 0:
        assert captured.err == ""
        document = json.loads(captured.out)
    else:
        assert captured.out == ""
        document = json.loads(captured.err)
    validation = ContractValidator().validate(document, "cli-result")
    assert validation.valid, validation.to_dict()
    return document


def sample_html(index: int = 1) -> str:
    return f"""<!doctype html>
<html><body><section id="js_content" style="max-width:677px;color:#222222;">
<p style="margin:0 8px 24px;font-size:16px;line-height:1.6;color:#222222;text-align:justify;letter-spacing:0.03em;">第一段正文用于建立可追溯的写作证据，并确保文本长度足以进入蒸馏分析。样本编号 {index}。</p>
<h2 style="margin:40px 8px 20px;font-size:24px;line-height:1.5;font-weight:700;color:#111111;">核心判断 {index}</h2>
<p style="margin:0 8px 24px;font-size:16px;line-height:1.6;color:#222222;text-align:justify;letter-spacing:0.03em;">第二段正文继续解释判断与证据之间的关系，同时维持相同的正文 inline style。</p>
</section></body></html>"""


def test_cli_full_mvp_lifecycle(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    initialized = invoke(capsys, tmp_path, "workspace", "init")
    assert initialized["command"] == "workspace.init"

    article = tmp_path / "article.md"
    article.write_text(
        """---
title: CLI 生命周期测试
---

::: lead
这是通过 CLI 创建并渲染的文章。
:::

正文包含 **重点判断**，用于验证富文本交付链。
""",
        encoding="utf-8",
    )
    created = invoke(
        capsys,
        tmp_path,
        "article",
        "create",
        "--name",
        "CLI 生命周期测试",
        "--mode",
        "layout_only",
        "--project-id",
        "cli-lifecycle",
        "--article-file",
        str(article),
    )
    assert created["data"]["project_id"] == "cli-lifecycle"
    project_root = Path(created["data"]["root"])

    inspected = invoke(capsys, tmp_path, "article", "inspect", "cli-lifecycle")
    assert inspected["data"]["paths"]["root"] == str(project_root)

    revised = tmp_path / "revised.md"
    revised.write_text("更新后的正文。", encoding="utf-8")
    updated = invoke(
        capsys,
        tmp_path,
        "article",
        "update",
        "cli-lifecycle",
        "--article-file",
        str(revised),
    )
    assert Path(updated["data"]["updated_files"][0]).read_text(encoding="utf-8") == (
        "更新后的正文。"
    )

    invoke(
        capsys,
        tmp_path,
        "article",
        "update",
        "cli-lifecycle",
        "--article-file",
        str(article),
    )

    validated = invoke(capsys, tmp_path, "article", "validate", "cli-lifecycle")
    assert validated["data"]["status"] == "PASS"

    rendered = invoke(capsys, tmp_path, "article", "render", "cli-lifecycle")
    assert rendered["data"]["status"] == "READY_FOR_USER_WECHAT_VALIDATION"
    assert all(Path(path).is_file() for path in rendered["data"]["generated_files"])

    validated_build = invoke(capsys, tmp_path, "article", "validate", "cli-lifecycle")
    assert validated_build["data"]["status"] == "PASS"

    collection = tmp_path / "samples"
    sample = tmp_path / "sample.html"
    sample.write_text(sample_html(), encoding="utf-8")
    imported_sample = invoke(
        capsys,
        tmp_path,
        "sample",
        "import",
        "--collection",
        str(collection),
        "--file",
        str(sample),
        "--kind",
        "html",
        "--article-type",
        "review",
        "--confirmed-by-user",
    )
    assert imported_sample["data"]["sample"]["sample_id"] == "SAMPLE-001"

    local_styles = project_root / "styles" / "local"
    analyzed = invoke(
        capsys,
        tmp_path,
        "sample",
        "analyze",
        "--collection",
        str(collection),
        "--candidate-id",
        "cli-editorial",
        "--candidate-name",
        "CLI Editorial",
        "--candidate-root",
        str(local_styles),
        "--publisher-or-author",
        "Reference Author",
    )
    candidate_path = Path(analyzed["data"]["candidate"]["path"])
    assert candidate_path.is_dir()
    assert analyzed["data"]["candidate"]["maturity"]["maturity"] == "provisional"

    style_validated = invoke(
        capsys, tmp_path, "style", "validate", str(candidate_path)
    )
    assert style_validated["data"]["record"]["status"] == "candidate"

    imported_candidate = invoke(
        capsys,
        tmp_path,
        "style",
        "import-candidate",
        "--source",
        str(candidate_path),
    )
    imports_path = Path(imported_candidate["data"]["path"])
    assert imports_path.parent == (tmp_path / "user" / "styles" / "imports").resolve()

    listed = invoke(
        capsys,
        tmp_path,
        "style",
        "list",
        "--project-root",
        str(project_root),
        "--include-candidates",
        "--include-imports",
    )
    assert any(
        item["style_pack_id"] == "cli-editorial"
        for item in listed["data"]["style_packs"]
    )

    promoted = invoke(
        capsys,
        tmp_path,
        "style",
        "promote",
        "--source",
        str(imports_path),
        "--confirmed-by-user",
    )
    private_path = Path(promoted["data"]["path"])
    assert private_path.parent == (tmp_path / "user" / "styles" / "private").resolve()
    assert promoted["data"]["reference"]["version"] == "0.1.0"

    archived = invoke(
        capsys,
        tmp_path,
        "style",
        "archive",
        "--source",
        str(private_path),
    )
    assert archived["data"]["record"]["status"] == "archived"

    preset = invoke(
        capsys,
        tmp_path,
        "style",
        "save-preset",
        "--id",
        "cli-preset",
        "--name",
        "CLI Preset",
        "--version",
        "1.0.0",
        "--layout-style-id",
        "basic-editorial",
        "--layout-style-version",
        "1.0.0",
        "--layout-style-layer",
        "builtin",
    )
    assert preset["data"]["document"]["status"] == "active"
    archived_preset = invoke(
        capsys,
        tmp_path,
        "style",
        "archive-preset",
        "--id",
        "cli-preset",
        "--version",
        "1.0.0",
    )
    assert archived_preset["data"]["document"]["status"] == "archived"

    migrated = invoke(capsys, tmp_path, "project", "migrate", "cli-lifecycle")
    assert migrated["data"]["changed"] is False
    assert migrated["data"]["source_version"] == "1.0"


def test_cli_standalone_writing_profile_lifecycle(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    collection = tmp_path / "text-samples"
    sample = tmp_path / "sample.txt"
    sample.write_text(
        "第一段用于建立写作节奏和论证结构。" * 8 + "\n\n" + "第二段用于验证纯文本只生成写作档案。" * 8,
        encoding="utf-8",
    )
    invoke(
        capsys,
        tmp_path,
        "sample",
        "import",
        "--collection",
        str(collection),
        "--file",
        str(sample),
        "--kind",
        "text",
        "--confirmed-by-user",
    )
    analyzed = invoke(
        capsys,
        tmp_path,
        "sample",
        "analyze",
        "--collection",
        str(collection),
        "--candidate-id",
        "plain-author",
        "--candidate-name",
        "Plain Author",
        "--candidate-root",
        str(tmp_path / "project" / "styles" / "local"),
    )
    candidate = Path(analyzed["data"]["candidate"]["path"])
    assert analyzed["data"]["candidate"]["kind"] == "writing_profile"

    imported = invoke(
        capsys,
        tmp_path,
        "style",
        "import-writing-profile",
        "--source",
        str(candidate),
    )
    assert imported["data"]["reference"]["layer"] == "imports"
    promoted = invoke(
        capsys,
        tmp_path,
        "style",
        "promote-writing-profile",
        "--id",
        "plain-author-writing",
        "--confirmed-by-user",
    )
    assert promoted["data"]["reference"]["layer"] == "private"
    archived = invoke(
        capsys,
        tmp_path,
        "style",
        "archive-writing-profile",
        "--id",
        "plain-author-writing",
        "--version",
        "0.1.0",
    )
    assert archived["data"]["document"]["status"] == "archived"


def test_preview_serve_emits_url_before_serving(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = tmp_path / "build"
    build.mkdir()
    (build / "wechat_preview.html").write_text("<!doctype html>", encoding="utf-8")
    events: list[str] = []

    class FakeServer:
        server_address = ("127.0.0.1", 54321)

        def serve_forever(self) -> None:
            events.append("served")

        def server_close(self) -> None:
            events.append("closed")

    monkeypatch.setattr(
        "wechat_studio_cli.commands.preview.create_preview_server",
        lambda build_directory, port=0: FakeServer(),
    )
    result = invoke(
        capsys,
        tmp_path,
        "preview",
        "serve",
        "--build-directory",
        str(build),
        "--no-open-browser",
    )

    assert result["data"]["url"] == "http://127.0.0.1:54321/wechat_preview.html"
    assert events == ["served", "closed"]


def test_cli_errors_use_stderr_and_stable_nonzero_exit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = invoke(
        capsys,
        tmp_path,
        "article",
        "inspect",
        "missing-project",
        expected_code=30,
    )

    assert error["ok"] is False
    assert error["command"] == "article.inspect"
    assert error["error"]["code"] == "WCS-PROJECT-002"


def test_cli_runs_from_arbitrary_working_directory(tmp_path: Path) -> None:
    elsewhere = tmp_path / "somewhere" / "else"
    elsewhere.mkdir(parents=True)
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(CORE_SRC), str(CLI_SRC), environment.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    command = [
        sys.executable,
        "-m",
        "wechat_studio_cli",
        "--format",
        "json",
        "--workspace",
        str(tmp_path / "external-user"),
        "--state-root",
        str(tmp_path / "external-state"),
        "--resources-root",
        str(RESOURCES),
        "workspace",
        "init",
    ]

    completed = subprocess.run(
        command,
        cwd=elsewhere,
        env=environment,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    document = json.loads(completed.stdout)
    assert document["command"] == "workspace.init"
    assert ContractValidator().validate(document, "cli-result").valid
