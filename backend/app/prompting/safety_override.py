"""
Safety override for WWJD mode — disables premium mode on crisis/high-risk.
"""
from __future__ import annotations

from app.safety import SafetyCheckResult


def should_override_wwjd(safety_result: SafetyCheckResult) -> bool:
    """
    Returns True if WWJD mode should be disabled for this turn.
    Safety always takes priority over premium features.
    """
    if safety_result.action in ("escalate", "refuse"):
        return True
    if safety_result.risk_level == "high":
        return True
    return False
