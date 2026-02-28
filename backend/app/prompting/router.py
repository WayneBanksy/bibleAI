"""
Prompt router — selects system/user prompt pair based on mode + safety context.
"""
from __future__ import annotations

from app.prompting.default_prompt import DEFAULT_SYSTEM_PROMPT, build_user_prompt
from app.prompting.safety_override import should_override_wwjd
from app.prompting.wwjd_prompt import WWJD_SYSTEM_PROMPT, WWJD_USER_TEMPLATE
from app.safety import SafetyCheckResult


def get_prompt_for_mode(
    mode: str,
    user_message: str,
    safety_result: SafetyCheckResult | None = None,
) -> tuple[str, str]:
    """
    Returns (system_prompt, user_prompt) for the given mode.
    If safety override applies, falls back to default mode.
    """
    if mode == "wwjd" and safety_result and should_override_wwjd(safety_result):
        mode = "default"

    if mode == "wwjd":
        return (
            WWJD_SYSTEM_PROMPT,
            WWJD_USER_TEMPLATE.format(user_message=user_message),
        )

    return (
        DEFAULT_SYSTEM_PROMPT,
        build_user_prompt(user_message=user_message),
    )
