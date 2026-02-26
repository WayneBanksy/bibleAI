"""
Pydantic validation for WWJD LLM structured output.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class WWJDDevotional(BaseModel):
    title: str = Field(max_length=80)
    reflection: str = Field(max_length=1200)
    action_steps: list[str] = Field(min_length=2, max_length=3)
    prayer: str = Field(max_length=500)

    @field_validator("action_steps")
    @classmethod
    def validate_action_steps(cls, v: list[str]) -> list[str]:
        forbidden_starts = [
            "you must", "you need to", "you should", "you have to", "do this", "stop",
        ]
        for step in v:
            if len(step) > 160:
                raise ValueError(f"Action step exceeds 160 chars: {len(step)}")
            if any(step.lower().startswith(f) for f in forbidden_starts):
                raise ValueError(f"Action step must be a suggestion, not a command: {step[:40]}...")
        return v


class WWJDVerseBlock(BaseModel):
    translation_id: str = Field(pattern=r"^(ESV|NIV|KJV|NKJV|NLT|CSB)$")
    book: str
    chapter: int = Field(ge=1)
    verse_start: int = Field(ge=1)
    verse_end: int = Field(ge=1)


class WWJDOutput(BaseModel):
    mode: str = Field(default="wwjd", pattern=r"^wwjd$")
    devotional: WWJDDevotional
    verse_block: WWJDVerseBlock | None = None


def validate_wwjd_output(raw_json: dict) -> WWJDOutput:
    """Validate and parse raw LLM JSON output into WWJD schema."""
    return WWJDOutput(**raw_json)
