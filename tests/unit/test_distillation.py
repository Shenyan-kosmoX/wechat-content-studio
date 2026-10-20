from __future__ import annotations

from pathlib import Path

import pytest

from wechat_studio.contracts import ContractValidator
from wechat_studio.distillation import (
    SampleRegistry,
    aggregate_evidence,
    analyze_html_evidence,
    analyze_text_evidence,
    assess_candidate_maturity,
    build_candidate,
    canonicalize_url,
)
from wechat_studio.errors import (
    DistillationInsufficientEvidenceError,
    SampleConflictError,
    SampleNotFoundError,
)
from wechat_studio.storage.yaml_io import read_yaml
from wechat_studio.styles import StylePack


ARTICLE_TEXT = (
    "这是第一段正文，用来说明一个清晰的问题，并提供足够长度的写作证据。"
    "它不会包含播放器、评论、点赞或分享控件的文字。"
)


def styled_html(*, body_size: int = 16, title: str = "核心判断") -> str:
    return f"""<!doctype html>
<html><body>
<section id="js_content" style="max-width:677px;color:#222222;">
  <p style="margin:0 8px 24px;font-size:{body_size}px;line-height:1.6;color:#222222;text-align:justify;letter-spacing:0.03em;">{ARTICLE_TEXT}</p>
  <section class="mp-common-video" style="font-size:99px;color:#ff0000;">
    <span>播放</span><span>1.0倍</span><span>00:10 / 03:20</span>
  </section>
  <div class="like_area" style="font-size:98px;color:#00ff00;">赞</div>
  <h2 style="margin:40px 8px 20px;font-size:24px;line-height:1.5;font-weight:700;color:#111111;">{title}</h2>
  <p style="margin:0 8px 24px;font-size:{body_size}px;line-height:1.6;color:#222222;text-align:justify;letter-spacing:0.03em;">这是第二段正文，它继续解释证据与结论之间的关系，并保持相同的正文排版。</p>
  <img data-src="https://mmbiz.qpic.cn/example.jpg" style="display:block;width:100%;height:auto;" />
</section>
</body></html>"""


def test_canonicalize_url_removes_tracking_and_normalizes_wechat() -> None:
    value = canonicalize_url(
        "http://MP.WEIXIN.QQ.COM/s/abc/?utm_source=x&scene=1&mid=2#fragment"
    )

    assert value == "https://mp.weixin.qq.com/s/abc?mid=2"


def test_sample_registry_allocates_stable_ids_and_deduplicates(tmp_path: Path) -> None:
    registry = SampleRegistry(tmp_path / "samples").initialize()

    first = registry.import_content(ARTICLE_TEXT, kind="text", title="A")
    duplicate = registry.import_content(ARTICLE_TEXT.replace("\n", "\r\n"), kind="text")
    url = registry.register_url("https://mp.weixin.qq.com/s/example?scene=1")

    assert first.created is True
    assert first.record["sample_id"] == "SAMPLE-001"
    assert duplicate.created is False
    assert duplicate.duplicate_of == "SAMPLE-001"
    assert url.record["sample_id"] == "SAMPLE-002"
    assert len(registry.list()) == 2


def test_same_canonical_url_with_different_content_is_a_conflict(tmp_path: Path) -> None:
    registry = SampleRegistry(tmp_path / "samples").initialize()
    url = "https://mp.weixin.qq.com/s/same?scene=1"
    registry.import_content(ARTICLE_TEXT, kind="html", source_url=url)

    with pytest.raises(SampleConflictError) as raised:
        registry.import_content(styled_html(), kind="html", source_url=url + "&from=share")

    assert raised.value.code == "WCS-SAMPLE-003"
    assert raised.value.context["canonical_url"] == "https://mp.weixin.qq.com/s/same"


def test_missing_sample_file_is_reported_without_manifest_entry(tmp_path: Path) -> None:
    registry = SampleRegistry(tmp_path / "samples").initialize()

    with pytest.raises(SampleNotFoundError) as raised:
        registry.import_path(tmp_path / "missing.html")

    assert raised.value.context["accessibility"] == "missing"
    assert registry.list() == []


def test_html_analysis_excludes_wechat_chrome_before_style_statistics() -> None:
    report = analyze_html_evidence("SAMPLE-001", styled_html(), article_type="review")

    assert report["evidence_scope"] == "writing_and_layout"
    assert report["layout"]["excluded_wechat_ui_subtrees"] == 2
    assert "99px" not in {
        row["value"]
        for row in report["layout"]["inline_style_values"]["font-size"]
    }
    assert "98px" not in {
        row["value"]
        for row in report["layout"]["inline_style_values"]["font-size"]
    }
    assert report["layout"]["component_occurrences"]["paragraph"] == 2
    assert report["layout"]["component_occurrences"]["image"] == 1


def test_unstyled_html_and_plain_text_never_claim_layout_evidence() -> None:
    html_report = analyze_html_evidence(
        "SAMPLE-001", f"<article><p>{ARTICLE_TEXT}</p></article>"
    )
    text_report = analyze_text_evidence(
        "SAMPLE-002", ARTICLE_TEXT + "\n\n" + ARTICLE_TEXT
    )

    assert html_report["evidence_scope"] == "writing_only"
    assert html_report["layout"] is None
    assert text_report["evidence_scope"] == "writing_only"
    assert text_report["layout"] is None


def test_registry_analysis_persists_scope_and_traceable_report(tmp_path: Path) -> None:
    registry = SampleRegistry(tmp_path / "samples").initialize()
    imported = registry.import_content(
        styled_html(),
        kind="html",
        title="Sample",
        article_type="tutorial",
        confirmed_by_user=True,
    )

    report = registry.analyze(imported.record["sample_id"])
    record = registry.get("SAMPLE-001")

    assert report["sample_id"] == "SAMPLE-001"
    assert record["analysis_status"] == "ready"
    assert record["evidence_scope"] == "writing_and_layout"
    assert (registry.root / record["analysis_path"]).is_file()


def test_aggregate_rules_keep_sample_ids_and_detect_conflicts() -> None:
    reports = [
        analyze_html_evidence(
            f"SAMPLE-{index:03d}",
            styled_html(body_size=16 if index <= 3 else 18, title=f"标题 {index}"),
            article_type="opinion",
        )
        for index in range(1, 7)
    ]

    aggregate = aggregate_evidence(reports)

    assert aggregate["sample_ids"] == [f"SAMPLE-{index:03d}" for index in range(1, 7)]
    assert aggregate["conflict_count"] >= 1
    assert all(
        item["sample_ids"]
        and set(item["sample_ids"]) <= set(aggregate["sample_ids"])
        for item in aggregate["layout"]["evidence"]
    )
    font_rule = next(
        item
        for item in aggregate["layout"]["evidence"]
        if item["rule_id"] == "LAYOUT-FONT-SIZE-001"
    )
    assert font_rule["confidence"] == "low"


def test_maturity_requires_quality_gates_and_explicit_review() -> None:
    small = assess_candidate_maturity(
        usable_sample_count=5,
        article_type_count=3,
        has_writing_evidence=True,
        has_layout_evidence=True,
        conflict_count=0,
        reviewed_for_established=True,
    )
    many_unreviewed = assess_candidate_maturity(
        usable_sample_count=9,
        article_type_count=3,
        has_writing_evidence=True,
        has_layout_evidence=True,
        conflict_count=0,
        reviewed_for_established=False,
    )
    established = assess_candidate_maturity(
        usable_sample_count=9,
        article_type_count=3,
        has_writing_evidence=True,
        has_layout_evidence=True,
        conflict_count=0,
        reviewed_for_established=True,
    )

    assert small.maturity == "provisional"
    assert many_unreviewed.maturity == "provisional"
    assert established.maturity == "established"


def test_text_only_candidate_is_a_standalone_writing_profile(tmp_path: Path) -> None:
    reports = [
        analyze_text_evidence(
            f"SAMPLE-{index:03d}", ARTICLE_TEXT + "\n\n" + ARTICLE_TEXT,
            article_type="essay",
        )
        for index in range(1, 4)
    ]
    aggregate = aggregate_evidence(reports)

    result = build_candidate(
        aggregate,
        tmp_path / "project" / "styles" / "local",
        style_id="plain-author",
        name="纯文本参考",
    )

    assert result.kind == "writing_profile"
    assert result.document["status"] == "provisional"
    assert result.path.name == "plain-author-writing-v0.1.0-candidate.1.yaml"
    assert not list((tmp_path / "project").rglob("layout-style.yaml"))
    assert ContractValidator().validate(result.document, "writing-profile").valid


def test_html_evidence_builds_schema_valid_project_candidate_pack(tmp_path: Path) -> None:
    reports = [
        analyze_html_evidence(
            f"SAMPLE-{index:03d}", styled_html(title=f"标题 {index}"),
            article_type=("opinion", "tutorial", "review")[index % 3],
        )
        for index in range(1, 6)
    ]
    aggregate = aggregate_evidence(reports)
    local_root = tmp_path / "article" / "styles" / "local"

    result = build_candidate(
        aggregate,
        local_root,
        style_id="learned-editorial",
        name="Learned Editorial",
        publisher_or_author="Reference Author",
        tags=["editorial"],
    )
    pack = StylePack.load(
        result.path, expected_layer="project", require_directory_name=True
    )

    assert result.kind == "style_pack"
    assert result.path.parent == local_root.resolve()
    assert pack.status == "candidate"
    assert pack.maturity == "provisional"
    assert pack.writing_profile is not None
    assert len(list(pack.components_directory.glob("*.html"))) == 12
    assert pack.document["provenance"]["sample_ids"] == [
        f"SAMPLE-{index:03d}" for index in range(1, 6)
    ]
    assert read_yaml(result.path / "validation.yaml")["wechat"]["status"] == (
        "AWAITING_USER_VALIDATION"
    )
    assert not (tmp_path / "styles" / "private").exists()


def test_candidate_generation_rejects_empty_evidence(tmp_path: Path) -> None:
    with pytest.raises(DistillationInsufficientEvidenceError):
        build_candidate(
            {
                "distillation_aggregate_version": "1.0",
                "sample_count": 1,
                "usable_sample_count": 0,
                "sample_ids": [],
                "article_types": [],
                "writing": None,
                "layout": None,
                "conflict_count": 0,
            },
            tmp_path,
            style_id="empty-style",
            name="Empty",
        )
