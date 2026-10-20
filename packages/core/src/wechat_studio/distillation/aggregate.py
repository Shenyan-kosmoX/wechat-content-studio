"""Aggregate independent sample evidence into candidate-ready style facts."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from statistics import median
from typing import Any, Iterable

from wechat_studio.errors import DistillationInvalidError

from .confidence import evidence_confidence, values_conflict


_NUMBER_UNIT = re.compile(r"^(-?\d+(?:\.\d+)?)(px|em|rem|%)?$", re.IGNORECASE)


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def _rule(
    rule_id: str,
    meaning: str,
    sample_ids: Iterable[str],
    usable_count: int,
    *,
    conflicting: bool = False,
) -> dict[str, Any]:
    evidence = sorted(set(sample_ids))
    return {
        "rule_id": rule_id,
        "meaning": meaning,
        "sample_ids": evidence,
        "confidence": evidence_confidence(
            len(evidence), usable_count, conflicting=conflicting
        ),
    }


def _ranked_coverage(
    value_samples: dict[str, set[str]], value_counts: Counter[str]
) -> list[dict[str, Any]]:
    rows = [
        {
            "value": value,
            "sample_count": len(sample_ids),
            "sample_ids": sorted(sample_ids),
            "occurrences": value_counts[value],
        }
        for value, sample_ids in value_samples.items()
    ]
    return sorted(
        rows,
        key=lambda row: (-row["sample_count"], -row["occurrences"], row["value"]),
    )


def _css_number(value: str) -> tuple[float, str] | None:
    match = _NUMBER_UNIT.fullmatch(value.strip())
    if not match:
        return None
    return float(match.group(1)), (match.group(2) or "").lower()


def _font_size(value: str | None, fallback: int = 16) -> int:
    parsed = _css_number(value or "")
    if parsed is None or parsed[1] != "px":
        return fallback
    return max(12, min(32, round(parsed[0])))


def _line_height(value: str | None, font_size: int, fallback: float = 1.6) -> float:
    parsed = _css_number(value or "")
    if parsed is None:
        return fallback
    number, unit = parsed
    if unit == "px":
        number = number / font_size
    elif unit == "%":
        number = number / 100
    elif unit in {"em", "rem"}:
        pass
    return round(max(1.0, min(3.0, number)), 3)


def _letter_spacing(value: str | None, font_size: int) -> float:
    parsed = _css_number(value or "")
    if parsed is None:
        return 0.0
    number, unit = parsed
    if unit == "px":
        number /= font_size
    elif unit == "%":
        number /= 100
    elif unit == "rem":
        number = number * 16 / font_size
    return round(max(0.0, min(0.5, number)), 3)


def _safe_color(value: str | None) -> str:
    color = (value or "").strip()
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", color) or re.fullmatch(
        r"rgba?\(.+\)", color, re.IGNORECASE
    ):
        return color
    short = re.fullmatch(r"#([0-9A-Fa-f])([0-9A-Fa-f])([0-9A-Fa-f])", color)
    if short:
        return "#" + "".join(character * 2 for character in short.groups())
    return "#222222"


def _writing_aggregate(reports: list[dict[str, Any]]) -> dict[str, Any] | None:
    writing_reports = [report for report in reports if report.get("writing")]
    if not writing_reports:
        return None
    usable = len(writing_reports)
    paragraph_lengths = [
        int(length)
        for report in writing_reports
        for length in report["writing"].get("paragraph_lengths", [])
        if isinstance(length, (int, float)) and length >= 0
    ]
    sentence_medians = [
        float(report["writing"].get("sentence_length_median", 0))
        for report in writing_reports
        if report["writing"].get("sentence_length_median", 0) > 0
    ]
    paragraph_medians = [
        float(report["writing"].get("paragraph_length_median", 0))
        for report in writing_reports
        if report["writing"].get("paragraph_length_median", 0) > 0
    ]
    opening_samples: dict[str, set[str]] = defaultdict(set)
    ending_samples: dict[str, set[str]] = defaultdict(set)
    for report in writing_reports:
        writing = report["writing"]
        opening_samples[writing["opening_pattern"]].add(report["sample_id"])
        ending_samples[writing["ending_pattern"]].add(report["sample_id"])

    opening = max(opening_samples, key=lambda value: (len(opening_samples[value]), value))
    ending = max(ending_samples, key=lambda value: (len(ending_samples[value]), value))
    paragraph_median = median(paragraph_medians) if paragraph_medians else 100
    if paragraph_median <= 80:
        pace = "brisk"
        pace_trait = "短段推进"
    elif paragraph_median <= 180:
        pace = "measured"
        pace_trait = "节奏克制"
    else:
        pace = "slow"
        pace_trait = "长段展开"

    if paragraph_medians and max(paragraph_medians) >= 1.8 * max(min(paragraph_medians), 1):
        variation = "high"
    elif paragraph_medians and max(paragraph_medians) >= 1.3 * max(min(paragraph_medians), 1):
        variation = "medium"
    else:
        variation = "low"

    all_ids = [report["sample_id"] for report in writing_reports]
    argument_structure = ["围绕核心主题逐层展开"]
    heading_ids = [
        report["sample_id"]
        for report in writing_reports
        if report["writing"].get("heading_count", 0) >= 2
    ]
    list_ids = [
        report["sample_id"]
        for report in writing_reports
        if report["writing"].get("list_item_count", 0) >= 2
    ]
    if heading_ids:
        argument_structure.append("通过分节切换核心论点或步骤")
    if list_ids:
        argument_structure.append("使用列表组织并列细节")

    rules = [
        _rule(
            "WRITE-PARAGRAPH-001",
            f"段落长度主要落在 {_percentile(paragraph_lengths, 0.2)}–{max(_percentile(paragraph_lengths, 0.8), 1)} 字。",
            all_ids,
            usable,
        ),
        _rule(
            "WRITE-OPENING-001",
            f"常见开头结构为 {opening}。",
            opening_samples[opening],
            usable,
        ),
        _rule(
            "WRITE-ENDING-001",
            f"常见结尾结构为 {ending}。",
            ending_samples[ending],
            usable,
        ),
        _rule(
            "WRITE-RHYTHM-001",
            f"段落中位长度约 {round(paragraph_median)} 字，整体节奏为 {pace}。",
            all_ids,
            usable,
        ),
    ]
    if heading_ids:
        rules.append(
            _rule(
                "WRITE-SECTIONS-001",
                "多篇样本通过分节推进论述。",
                heading_ids,
                usable,
            )
        )
    if list_ids:
        rules.append(
            _rule(
                "WRITE-LISTS-001",
                "部分样本使用列表组织并列信息。",
                list_ids,
                usable,
            )
        )

    minimum = max(0, min(2000, _percentile(paragraph_lengths, 0.2)))
    maximum = max(1, min(5000, _percentile(paragraph_lengths, 0.8)))
    maximum = max(maximum, minimum)
    return {
        "sample_ids": sorted(all_ids),
        "tone_traits": ["结构清晰", pace_trait],
        "tone_avoid": ["复制参考样本原句或标志性表达"],
        "pace": pace,
        "sentence_variation": variation,
        "sentence_length_median": round(median(sentence_medians), 2)
        if sentence_medians
        else 0,
        "paragraph_minimum": minimum,
        "paragraph_maximum": maximum,
        "argument_structure": argument_structure,
        "opening_patterns": [opening],
        "ending_patterns": [ending],
        "evidence": rules,
    }


def _layout_aggregate(reports: list[dict[str, Any]]) -> dict[str, Any] | None:
    layout_reports = [report for report in reports if report.get("layout")]
    if not layout_reports:
        return None
    usable = len(layout_reports)
    property_samples: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    property_counts: dict[str, Counter[str]] = defaultdict(Counter)
    body_property_samples: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    body_property_counts: dict[str, Counter[str]] = defaultdict(Counter)
    width_samples: dict[str, set[str]] = defaultdict(set)
    width_counts: Counter[str] = Counter()
    component_signatures: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    for report in layout_reports:
        sample_id = report["sample_id"]
        layout = report["layout"]
        for property_name, rows in layout.get("inline_style_values", {}).items():
            for row in rows:
                value = str(row["value"])
                property_samples[property_name][value].add(sample_id)
                property_counts[property_name][value] += int(row["count"])
        for width in layout.get("width_candidates_px", []):
            value = str(int(width))
            width_samples[value].add(sample_id)
            width_counts[value] += 1
        for component, candidates in layout.get("component_candidates", {}).items():
            for candidate in candidates:
                signature = candidate["signature"]
                stored = component_signatures[component].setdefault(
                    signature,
                    {
                        "signature": signature,
                        "tag": candidate["tag"],
                        "style": dict(candidate["style"]),
                        "sample_ids": set(),
                        "occurrences": 0,
                        "positions": set(),
                    },
                )
                stored["sample_ids"].add(sample_id)
                stored["occurrences"] += int(candidate["occurrences"])
                stored["positions"].update(candidate.get("positions", []))
                if component == "paragraph":
                    for property_name, value in candidate.get("style", {}).items():
                        body_property_samples[property_name][str(value)].add(sample_id)
                        body_property_counts[property_name][str(value)] += int(
                            candidate["occurrences"]
                        )

    property_rankings = {
        name: _ranked_coverage(values, property_counts[name])
        for name, values in sorted(property_samples.items())
    }
    body_property_rankings = {
        name: _ranked_coverage(values, body_property_counts[name])
        for name, values in sorted(body_property_samples.items())
    }
    conflicts: list[dict[str, Any]] = []
    for property_name, rows in body_property_rankings.items():
        if len(rows) >= 2 and values_conflict(
            rows[0]["sample_count"], rows[1]["sample_count"]
        ):
            conflicts.append(
                {
                    "kind": "body_property",
                    "property": property_name,
                    "values": [rows[0], rows[1]],
                }
            )

    def selected(property_name: str) -> str | None:
        rows = body_property_rankings.get(property_name, [])
        if not rows:
            rows = property_rankings.get(property_name, [])
        return rows[0]["value"] if rows else None

    font_size = _font_size(selected("font-size"))
    line_height = _line_height(selected("line-height"), font_size)
    text_align = (selected("text-align") or "left").lower()
    if text_align not in {"left", "center", "right", "justify"}:
        text_align = "left"
    width_ranking = _ranked_coverage(width_samples, width_counts)
    max_width = int(width_ranking[0]["value"]) if width_ranking else 677
    root = {
        "max_width_px": max(320, min(1200, max_width)),
        "font_size_px": font_size,
        "line_height": line_height,
        "text_color": _safe_color(selected("color")),
        "text_align": text_align,
        "letter_spacing_em": _letter_spacing(selected("letter-spacing"), font_size),
    }

    component_profiles: dict[str, dict[str, Any]] = {}
    for component, signatures in sorted(component_signatures.items()):
        rows = sorted(
            signatures.values(),
            key=lambda row: (
                -len(row["sample_ids"]),
                -row["occurrences"],
                row["signature"],
            ),
        )
        winner = rows[0]
        conflicting = len(rows) >= 2 and values_conflict(
            len(winner["sample_ids"]), len(rows[1]["sample_ids"])
        )
        if conflicting:
            conflicts.append(
                {
                    "kind": "component_style",
                    "component": component,
                    "signatures": [
                        {
                            "signature": row["signature"],
                            "sample_ids": sorted(row["sample_ids"]),
                            "sample_count": len(row["sample_ids"]),
                        }
                        for row in rows[:2]
                    ],
                }
            )
        component_profiles[component] = {
            "tag": winner["tag"],
            "style": winner["style"],
            "sample_ids": sorted(winner["sample_ids"]),
            "sample_count": len(winner["sample_ids"]),
            "occurrences": winner["occurrences"],
            "positions": sorted(winner["positions"]),
            "confidence": evidence_confidence(
                len(winner["sample_ids"]), usable, conflicting=conflicting
            ),
        }

    all_ids = sorted(report["sample_id"] for report in layout_reports)
    evidence: list[dict[str, Any]] = []
    property_rules = (
        ("font-size", "LAYOUT-FONT-SIZE-001", f"正文主字号候选为 {font_size}px。"),
        ("line-height", "LAYOUT-LINE-HEIGHT-001", f"正文主行高候选为 {line_height}。"),
        ("color", "LAYOUT-TEXT-COLOR-001", f"正文主文字颜色候选为 {root['text_color']}。"),
        ("text-align", "LAYOUT-TEXT-ALIGN-001", f"正文主对齐方式候选为 {text_align}。"),
    )
    conflict_properties = {
        item["property"] for item in conflicts if item["kind"] == "body_property"
    }
    for property_name, rule_id, meaning in property_rules:
        rows = body_property_rankings.get(property_name, [])
        if not rows:
            rows = property_rankings.get(property_name, [])
        if rows:
            evidence.append(
                _rule(
                    rule_id,
                    meaning,
                    rows[0]["sample_ids"],
                    usable,
                    conflicting=property_name in conflict_properties,
                )
            )
    if width_ranking:
        evidence.append(
            _rule(
                "LAYOUT-MAX-WIDTH-001",
                f"正文最大宽度候选为 {root['max_width_px']}px。",
                width_ranking[0]["sample_ids"],
                usable,
            )
        )
    for component, profile in component_profiles.items():
        rule_id = "LAYOUT-COMPONENT-" + component.replace("_", "-").upper()
        evidence.append(
            _rule(
                rule_id,
                f"{component} 组件存在跨样本可复用的 inline-style 候选。",
                profile["sample_ids"],
                usable,
                conflicting=any(
                    item.get("component") == component for item in conflicts
                ),
            )
        )

    return {
        "sample_ids": all_ids,
        "root": root,
        "property_rankings": property_rankings,
        "body_property_rankings": body_property_rankings,
        "component_profiles": component_profiles,
        "evidence": evidence,
        "conflicts": conflicts,
    }


def aggregate_evidence(reports: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate reports while preserving independent SAMPLE provenance."""

    materialized = list(reports)
    ids = [str(report.get("sample_id", "")) for report in materialized]
    if len(ids) != len(set(ids)):
        raise DistillationInvalidError(
            "Evidence reports contain duplicate sample IDs.",
            context={"sample_ids": ids},
        )
    usable = [
        report
        for report in materialized
        if report.get("accessibility") == "accessible"
        and report.get("evidence_scope") != "none"
    ]
    writing = _writing_aggregate(usable)
    layout = _layout_aggregate(usable)
    article_types = sorted(
        {
            str(report.get("article_type", "other"))
            for report in usable
            if report.get("article_type")
        }
    )
    conflicts = list(layout.get("conflicts", [])) if layout else []
    return {
        "distillation_aggregate_version": "1.0",
        "sample_count": len(materialized),
        "usable_sample_count": len(usable),
        "sample_ids": sorted(report["sample_id"] for report in usable),
        "writing_sample_ids": writing["sample_ids"] if writing else [],
        "layout_sample_ids": layout["sample_ids"] if layout else [],
        "article_types": article_types,
        "writing": writing,
        "layout": layout,
        "conflicts": conflicts,
        "conflict_count": len(conflicts),
    }
