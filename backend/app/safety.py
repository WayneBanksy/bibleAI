"""
Safety classifiers: keyword pre-check + Claude LLM post-check.

Architecture:
  - KeywordSafetyClassifier: fast, synchronous keyword regex (pre-check)
  - LLMSafetyClassifier: thorough, Claude-powered analysis (post-check)
  - SafetyClassifier protocol allows injection in pipeline call sites.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import structlog

log = structlog.get_logger()


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


# ---------------------------------------------------------------------------
# LLM-based safety classifier (post-check — Claude powered)
# ---------------------------------------------------------------------------

_SAFETY_SYSTEM_PROMPT = """You are a safety classifier for a Bible-grounded reflection app.
Your job is to analyze text (either user messages or assistant-generated responses) for safety violations.

You MUST return valid JSON only. No surrounding text.

## JSON Schema
{
  "risk_level": "none" | "low" | "medium" | "high",
  "categories": ["self_harm", "abuse", "medical_advice", "hate", "sexual", "violence", "spiritual_coercion", "citation_integrity"],
  "action": "allow" | "caution" | "refuse" | "escalate",
  "rationale_codes": ["short_code_1", "short_code_2"]
}

## Classification Rules

### ESCALATE (risk_level: "high", action: "escalate"):
- Active suicidal ideation or self-harm intent
- Statements about wanting to die or end their life
- Disclosure of ongoing abuse (child, domestic, elder)
- Imminent danger to self or others

### REFUSE (risk_level: "medium", action: "refuse"):
- Requests for specific medical/psychiatric diagnosis
- Requests for medication advice or dosage information
- Content that provides treatment recommendations
- Assistant output containing prohibited clinical language (diagnosis, treatment plans)
- Assistant output containing spiritual coercion (divine punishment threats, shame spirals, "you must believe or else")

### CAUTION (risk_level: "low", action: "caution"):
- Mentions of trauma, abuse history (non-imminent)
- General anxiety, depression references
- Assistant output with mildly prescriptive religious language

### ALLOW (risk_level: "none", action: "allow"):
- General life questions, spiritual curiosity
- Grief, sadness, loneliness (non-crisis)
- Normal faith discussion

## Critical: For assistant output post-check, also flag:
- Diagnostic language ("You have depression", "You may be bipolar")
- Treatment advice ("Try CBT", "See a trauma therapist")
- Spiritual coercion ("God will punish you", "You must have more faith")
- Divine certainty claims ("God told me you will be healed")
- Proof-texting to dismiss grief or trauma
"""


class LLMSafetyClassifier:
    """
    Claude-powered safety classifier for thorough post-check analysis.

    Used as the post-check stage in the pipeline to catch:
    - Subtle crisis signals missed by keyword matching
    - Prohibited clinical language in assistant output
    - Spiritual coercion patterns in assistant output
    """

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key

    def _get_client(self):
        """Lazy import to avoid circular dependency with config."""
        import anthropic
        from app.config import settings
        key = self._api_key or settings.anthropic_api_key
        return anthropic.Anthropic(api_key=key)

    def classify(self, text: str) -> SafetyCheckResult:
        """
        Classify text using Claude for thorough safety analysis.
        Falls back to allow on any error (fail-open for post-check;
        keyword pre-check already caught obvious signals).
        """
        try:
            return self._classify_with_llm(text)
        except Exception as exc:
            log.warning("safety.llm_classifier_error", error=str(exc))
            # Fail-open: keyword pre-check already ran
            return SafetyCheckResult(
                risk_level="none",
                categories=[],
                action="allow",
                rationale_codes=["llm_classifier_error"],
            )

    def _classify_with_llm(self, text: str) -> SafetyCheckResult:
        """Make the actual Claude API call for safety classification."""
        client = self._get_client()

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",  # Fast + cheap for classification
            max_tokens=200,
            system=_SAFETY_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Classify the following text for safety:\n\n{text}",
            }],
            timeout=10.0,
        )

        raw_text = ""
        for block in response.content:
            if block.type == "text":
                raw_text += block.text

        parsed = json.loads(raw_text)

        return SafetyCheckResult(
            risk_level=parsed.get("risk_level", "none"),
            categories=parsed.get("categories", []),
            action=parsed.get("action", "allow"),
            rationale_codes=[f"llm:{code}" for code in parsed.get("rationale_codes", [])],
        )


# Module-level singletons used by the pipeline.
default_classifier: SafetyClassifier = KeywordSafetyClassifier()
llm_classifier: LLMSafetyClassifier = LLMSafetyClassifier()
