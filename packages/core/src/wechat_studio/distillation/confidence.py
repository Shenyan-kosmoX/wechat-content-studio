"""Deterministic confidence and maturity gates for distilled evidence."""

from __future__ import annotations

from dataclasses import dataclass


CONFIDENCE_LEVELS = ("low", "medium", "high")


def evidence_confidence(
    support_count: int,
    usable_sample_count: int,
    *,
    conflicting: bool = False,
) -> str:
    """Rate one rule from independent sample coverage, never raw DOM frequency."""

    if support_count <= 0 or usable_sample_count <= 0:
        return "low"
    coverage = support_count / usable_sample_count
    if support_count >= 5 and coverage >= 0.6:
        level = "high"
    elif support_count >= 3 and coverage >= 0.35:
        level = "medium"
    else:
        level = "low"
    if not conflicting:
        return level
    return {"high": "medium", "medium": "low", "low": "low"}[level]


def values_conflict(
    first_support: int,
    second_support: int,
    *,
    threshold: float = 0.75,
) -> bool:
    """Return true when two different values have similarly broad support."""

    if first_support <= 0 or second_support <= 0:
        return False
    return second_support / first_support >= threshold


@dataclass(frozen=True, slots=True)
class MaturityAssessment:
    maturity: str
    eligible_for_established: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "maturity": self.maturity,
            "eligible_for_established": self.eligible_for_established,
            "reasons": list(self.reasons),
        }


def assess_candidate_maturity(
    *,
    usable_sample_count: int,
    article_type_count: int,
    has_writing_evidence: bool,
    has_layout_evidence: bool,
    conflict_count: int,
    reviewed_for_established: bool = False,
) -> MaturityAssessment:
    """Apply the evidence gates described by the product design.

    Eight samples are necessary but deliberately insufficient on their own.
    A candidate becomes ``established`` only after an explicit review flag and
    evidence diversity/quality gates all pass.
    """

    reasons: list[str] = []
    if usable_sample_count < 8:
        reasons.append("fewer_than_8_usable_samples")
    if article_type_count < 3:
        reasons.append("article_type_coverage_below_3")
    if not has_writing_evidence:
        reasons.append("missing_writing_evidence")
    if not has_layout_evidence:
        reasons.append("missing_layout_evidence")
    if conflict_count:
        reasons.append("unresolved_evidence_conflicts")
    if not reviewed_for_established:
        reasons.append("established_review_not_confirmed")

    eligible = not reasons
    return MaturityAssessment(
        maturity="established" if eligible else "provisional",
        eligible_for_established=eligible,
        reasons=tuple(reasons),
    )
