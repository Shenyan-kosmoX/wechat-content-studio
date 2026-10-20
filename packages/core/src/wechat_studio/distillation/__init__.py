"""Evidence-bound style distillation APIs."""

from .aggregate import aggregate_evidence
from .candidate import CandidateBuildResult, build_candidate
from .confidence import MaturityAssessment, assess_candidate_maturity, evidence_confidence
from .html_evidence import analyze_html_evidence, analyze_text_evidence, parse_style
from .samples import SampleImportResult, SampleRegistry, canonicalize_url

__all__ = [
    "CandidateBuildResult",
    "MaturityAssessment",
    "SampleImportResult",
    "SampleRegistry",
    "aggregate_evidence",
    "analyze_html_evidence",
    "analyze_text_evidence",
    "assess_candidate_maturity",
    "build_candidate",
    "canonicalize_url",
    "evidence_confidence",
    "parse_style",
]
