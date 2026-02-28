"""
P2-01 WWJD Mode — pure unit tests (no DB, no async).
"""
import pytest
from pydantic import ValidationError

from app.prompting.default_prompt import DEFAULT_SYSTEM_PROMPT, build_user_prompt
from app.prompting.router import get_prompt_for_mode
from app.prompting.safety_override import should_override_wwjd
from app.prompting.wwjd_prompt import WWJD_SYSTEM_PROMPT, WWJD_USER_TEMPLATE
from app.prompting.wwjd_schema import WWJDOutput, validate_wwjd_output
from app.safety import SafetyCheckResult


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------

def test_wwjd_prompt_renders():
    assert "WWJD" in WWJD_SYSTEM_PROMPT
    assert "suggestions" in WWJD_SYSTEM_PROMPT.lower() or "Consider" in WWJD_SYSTEM_PROMPT
    rendered = WWJD_USER_TEMPLATE.format(user_message="I feel lost")
    assert "I feel lost" in rendered


def test_default_prompt_renders():
    assert "Bible-grounded" in DEFAULT_SYSTEM_PROMPT
    rendered = build_user_prompt(user_message="Help me pray")
    assert "Help me pray" in rendered


# ---------------------------------------------------------------------------
# WWJD schema validation
# ---------------------------------------------------------------------------

_VALID_WWJD = {
    "mode": "wwjd",
    "devotional": {
        "title": "Walking in Compassion",
        "reflection": "Jesus consistently showed compassion to those who were hurting.",
        "action_steps": [
            "Consider reaching out to someone who might be going through a similar experience.",
            "You might spend a few minutes in quiet prayer about this situation.",
        ],
        "prayer": "Lord, help me see others with your eyes of compassion.",
    },
    "verse_block": {
        "translation_id": "NIV",
        "book": "Matthew",
        "chapter": 5,
        "verse_start": 7,
        "verse_end": 7,
    },
}


def test_wwjd_schema_valid_output():
    result = validate_wwjd_output(_VALID_WWJD)
    assert result.mode == "wwjd"
    assert len(result.devotional.action_steps) == 2
    assert result.verse_block is not None


def test_wwjd_schema_missing_devotional():
    with pytest.raises(ValidationError):
        validate_wwjd_output({"mode": "wwjd"})


def test_wwjd_schema_action_steps_too_few():
    data = {**_VALID_WWJD, "devotional": {**_VALID_WWJD["devotional"], "action_steps": ["One step only"]}}
    with pytest.raises(ValidationError):
        validate_wwjd_output(data)


def test_wwjd_schema_action_steps_too_many():
    steps = [f"Step {i}" for i in range(4)]
    data = {**_VALID_WWJD, "devotional": {**_VALID_WWJD["devotional"], "action_steps": steps}}
    with pytest.raises(ValidationError):
        validate_wwjd_output(data)


def test_wwjd_schema_action_step_too_long():
    steps = ["x" * 161, "Consider a short step"]
    data = {**_VALID_WWJD, "devotional": {**_VALID_WWJD["devotional"], "action_steps": steps}}
    with pytest.raises(ValidationError):
        validate_wwjd_output(data)


def test_wwjd_schema_imperative_rejected():
    steps = ["You must repent immediately", "Consider praying about it"]
    data = {**_VALID_WWJD, "devotional": {**_VALID_WWJD["devotional"], "action_steps": steps}}
    with pytest.raises(ValidationError):
        validate_wwjd_output(data)


def test_wwjd_schema_verse_block_optional():
    data = {**_VALID_WWJD, "verse_block": None}
    result = validate_wwjd_output(data)
    assert result.verse_block is None


def test_wwjd_schema_invalid_translation():
    data = {**_VALID_WWJD, "verse_block": {**_VALID_WWJD["verse_block"], "translation_id": "MSG"}}
    with pytest.raises(ValidationError):
        validate_wwjd_output(data)


def test_wwjd_schema_reflection_too_long():
    data = {**_VALID_WWJD, "devotional": {**_VALID_WWJD["devotional"], "reflection": "x" * 1201}}
    with pytest.raises(ValidationError):
        validate_wwjd_output(data)


def test_wwjd_schema_title_too_long():
    data = {**_VALID_WWJD, "devotional": {**_VALID_WWJD["devotional"], "title": "x" * 81}}
    with pytest.raises(ValidationError):
        validate_wwjd_output(data)


# ---------------------------------------------------------------------------
# Safety override
# ---------------------------------------------------------------------------

def test_safety_override_escalate():
    result = SafetyCheckResult(risk_level="high", categories=["self_harm"], action="escalate")
    assert should_override_wwjd(result) is True


def test_safety_override_refuse():
    result = SafetyCheckResult(risk_level="medium", categories=["medical_advice"], action="refuse")
    assert should_override_wwjd(result) is True


def test_safety_override_high_risk():
    result = SafetyCheckResult(risk_level="high", categories=["violence"], action="caution")
    assert should_override_wwjd(result) is True


def test_safety_override_allow():
    result = SafetyCheckResult(risk_level="low", categories=[], action="allow")
    assert should_override_wwjd(result) is False


def test_safety_override_none_risk():
    result = SafetyCheckResult(risk_level="none", categories=[], action="allow")
    assert should_override_wwjd(result) is False


# ---------------------------------------------------------------------------
# Prompt router
# ---------------------------------------------------------------------------

def test_prompt_router_wwjd_mode():
    sys_prompt, user_prompt = get_prompt_for_mode("wwjd", "test message")
    assert sys_prompt == WWJD_SYSTEM_PROMPT
    assert "test message" in user_prompt


def test_prompt_router_default_mode():
    sys_prompt, user_prompt = get_prompt_for_mode("default", "test message")
    assert sys_prompt == DEFAULT_SYSTEM_PROMPT
    assert "test message" in user_prompt


def test_prompt_router_wwjd_with_crisis_override():
    crisis = SafetyCheckResult(risk_level="high", categories=["self_harm"], action="escalate")
    sys_prompt, user_prompt = get_prompt_for_mode("wwjd", "test", safety_result=crisis)
    assert sys_prompt == DEFAULT_SYSTEM_PROMPT  # fell back to default
