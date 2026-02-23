"""
Safety classifier: keyword-based stub for dev/testing.

Architecture: SafetyClassifier protocol allows swapping to a real ML
classifier (T015) without changing the pipeline call sites.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# SafetyCheckResult — matches INTERFACES.md §8
# ---------------------------------------------------------------------------

@dataclass
class SafetyCheckResult:
    risk_level: str          # "none" | "low" | "medium" | "high"
    categories: list[str]    # see INTERFACES.md §8 enum
    action: str              # "allow" | "caution" | "refuse" | "escalate"
    rationale_codes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Protocol (injectable — real ML classifier must satisfy this)
# ---------------------------------------------------------------------------

@runtime_checkable
class SafetyClassifier(Protocol):
    def classify(self, text: str) -> SafetyCheckResult:
        ...


# ---------------------------------------------------------------------------
# Keyword-based stub (dev only — NOT production quality)
# ---------------------------------------------------------------------------

_ESCALATE_PATTERNS: list[tuple[str, str]] = [
    # (regex, category)
    (r"\b(kill|hurt|harm|end)\s+(my|your)?(self|life)\b", "self_harm"),
    (r"\bsuicid(e|al)\b", "self_harm"),
    (r"\bself.?harm\b", "self_harm"),
    (r"\bwant to (hurt|kill|harm) (someone|others|people|him|her|them)\b", "violence"),
    (r"\b(murder|assault|attack) (someone|people)\b", "violence"),
]

_REFUSE_PATTERNS: list[tuple[str, str]] = [
    (r"\b(what|which) (medication|drug|medicine|pill|dose|dosage)\b", "medical_advice"),
    (r"\bshould i (take|stop|start) (medication|drug|medicine)\b", "medical_advice"),
    (r"\b(prescri|diagnos)\w+\b", "medical_advice"),
]

_CAUTION_PATTERNS: list[tuple[str, str]] = [
    (r"\b(abus(e|ed|ing)|trauma|assault(ed)?)\b", "abuse"),
    (r"\b(anxi(ety|ous)|depressed|depression)\b", "self_harm"),
]


class KeywordSafetyClassifier:
    """
    Keyword-based safety classifier for dev/test.
    Replace with a real ML classifier in production.
    """

    def classify(self, text: str) -> SafetyCheckResult:
        lowered = text.lower()

        # Escalate check (highest priority)
        for pattern, category in _ESCALATE_PATTERNS:
            if re.search(pattern, lowered):
                return SafetyCheckResult(
                    risk_level="high",
                    categories=[category],
                    action="escalate",
                    rationale_codes=[f"kw_escalate:{category}"],
                )

        # Refuse check
        for pattern, category in _REFUSE_PATTERNS:
            if re.search(pattern, lowered):
                return SafetyCheckResult(
                    risk_level="medium",
                    categories=[category],
                    action="refuse",
                    rationale_codes=[f"kw_refuse:{category}"],
                )

        # Caution check
        for pattern, category in _CAUTION_PATTERNS:
            if re.search(pattern, lowered):
                return SafetyCheckResult(
                    risk_level="low",
                    categories=[category],
                    action="caution",
                    rationale_codes=[f"kw_caution:{category}"],
                )

        # Sad / distressed but not escalating
        if re.search(r"\b(sad|lonely|alone|hopeless|overwhelm|grief|griev|mourn|cry|tears)\b", lowered):
            return SafetyCheckResult(
                risk_level="low",
                categories=[],
                action="allow",
                rationale_codes=["kw_low_distress"],
            )

        return SafetyCheckResult(
            risk_level="none",
            categories=[],
            action="allow",
            rationale_codes=[],
        )


# Module-level singleton used by the pipeline.
default_classifier: SafetyClassifier = KeywordSafetyClassifier()
