"""
Message processing pipeline.

Stages (in order):
  1. pre_check  — safety pre-check; escalate/refuse short-circuits the pipeline
  2. encrypt    — AES-256-GCM encrypt user text + compute SHA-256 hash
  3. llm_call   — call LLM provider (Claude/stub) via provider abstraction
  4. validate   — parse + schema-validate LLM output
  5. citations  — validate verse_block against bible_verses DB (T010)
  6. post_check — safety post-check on generated reflection
  7. emit       — stream token.delta events then message.final

B002 compliance
---------------
⚠️  PLACEHOLDER — DO NOT SHIP without T012 (Mental Health Advisor) signoff.
    Replace CRISIS_TEMPLATE_PLACEHOLDER with reviewed copy from
    SAFETY_POLICY.md §2.3 after T012 is resolved.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.citation import CitationResult, validate_citations
from app.crypto import message_crypto
from app.llm import (
    LLMError,
    LLMOutputError,
    LLMRateLimitError,
    LLMTimeoutError,
    get_llm_provider,
)
from app.models import Message, SafetyEvent, VerseCitation
from app.prompting.default_prompt import DEFAULT_SYSTEM_PROMPT, build_user_prompt
from app.safety import SafetyCheckResult, SafetyClassifier, default_classifier
from app.schemas import (
    CitationPayload,
    MessageFinalPayload,
    ResourceItem,
    RiskInterruptPayload,
    RiskPayload,
    StreamErrorPayload,
    StructuredPayload,
    TokenDeltaPayload,
)
from app.streaming import _sse

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# B002 — Crisis template placeholder
# ⚠️  DO NOT REPLACE until T012 (Mental Health Advisor) signoff is recorded
#      in governance/TASKS.md T012.
# ---------------------------------------------------------------------------
CRISIS_TEMPLATE_PLACEHOLDER = (
    "[CRISIS RESPONSE COPY PENDING CLINICAL REVIEW — T012 REQUIRED BEFORE SHIP]"
)
CRISIS_RESOURCES: list[dict[str, str]] = [
    {"label": "988 Suicide & Crisis Lifeline", "contact": "Call or text 988"},
    {"label": "Crisis Text Line", "contact": "Text HOME to 741741"},
    {"label": "Emergency Services", "contact": "Call 911"},
]



# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_pipeline(
    *,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    user_message_id: uuid.UUID,
    assistant_message_id: uuid.UUID,
    text: str,
    db: AsyncSession,
    queue: asyncio.Queue,
    classifier: SafetyClassifier = default_classifier,
) -> None:
    """
    Full message processing pipeline. Puts SSE event strings into `queue`.
    Called as a background task from the messages router.
    Never raises — all errors are emitted as stream.error events.
    """
    ctx = log.bind(
        session_id=str(session_id),
        user_msg_id=str(user_message_id),
        assistant_msg_id=str(assistant_message_id),
    )

    try:
        # ------------------------------------------------------------------
        # 1. Pre-check
        # ------------------------------------------------------------------
        pre_result = classifier.classify(text)
        model_version = "pending"  # Updated in stage 3 after LLM call
        await _log_safety_event(
            db, assistant_message_id, "pre", pre_result, model_version
        )

        if pre_result.action == "escalate":
            ctx.info("pipeline.escalate", risk_level=pre_result.risk_level)
            await _emit_risk_interrupt(queue, pre_result)
            return

        if pre_result.action == "refuse":
            ctx.info("pipeline.refuse", risk_level=pre_result.risk_level)
            await _emit_stream_error(
                queue,
                code="refused",
                message="This request cannot be processed.",
                retryable=False,
            )
            return

        # ------------------------------------------------------------------
        # 2. Encrypt + persist user message text
        # ------------------------------------------------------------------
        encrypted = message_crypto.encrypt(user_id, text)
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        await _update_user_message(db, user_message_id, encrypted, text_hash)

        # ------------------------------------------------------------------
        # 3. LLM call (via provider abstraction)
        # ------------------------------------------------------------------
        from app.config import settings

        provider = get_llm_provider()
        system_prompt = DEFAULT_SYSTEM_PROMPT
        user_prompt = build_user_prompt(user_message=text)

        try:
            llm_response = await provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                rag_context=None,  # RAG deferred until B005 resolved
                timeout_seconds=settings.llm_timeout_seconds,
                max_output_tokens=settings.llm_max_output_tokens,
            )
            raw_json = llm_response.raw_json
            model_version = llm_response.model_version
        except LLMTimeoutError:
            ctx.warning("pipeline.llm_timeout")
            await _emit_stream_error(
                queue,
                code="llm_timeout",
                message="Response generation timed out. Please try again.",
                retryable=True,
            )
            return
        except LLMRateLimitError:
            ctx.warning("pipeline.llm_rate_limit")
            await _emit_stream_error(
                queue,
                code="llm_rate_limit",
                message="Service is busy. Please try again in a moment.",
                retryable=True,
            )
            return
        except LLMOutputError:
            ctx.warning("pipeline.llm_output_error")
            await _emit_stream_error(
                queue,
                code="llm_output_invalid",
                message="Unable to generate a valid response.",
                retryable=True,
            )
            return
        except LLMError as exc:
            ctx.error("pipeline.llm_error", error=str(exc))
            await _emit_stream_error(
                queue,
                code="llm_error",
                message="An error occurred generating your response.",
                retryable=exc.retryable,
            )
            return

        # ------------------------------------------------------------------
        # 4. Validate LLM output
        # ------------------------------------------------------------------
        try:
            llm_output = _validate_llm_output(raw_json)
        except ValueError as exc:
            ctx.error("pipeline.llm_output_invalid", error=str(exc))
            await _emit_stream_error(
                queue,
                code="llm_output_invalid",
                message="Unable to generate a valid response.",
                retryable=True,
            )
            return

        reflection: str = llm_output["reflection"]
        verse_block: list[dict] = llm_output.get("verse_block", [])
        prayer: str | None = llm_output.get("prayer")
        next_step: str | None = llm_output.get("next_step")
        reflection_question: str | None = llm_output.get("reflection_question")

        # ------------------------------------------------------------------
        # 5. Citation gate (T010)
        # ------------------------------------------------------------------
        citation_results = await _run_citation_gate(verse_block, db, ctx)
        validated_citations = [r for r in citation_results if r.validated]

        # Log stripped citations
        for r in citation_results:
            if not r.validated:
                await _log_safety_event(
                    db,
                    assistant_message_id,
                    "post",
                    SafetyCheckResult(
                        risk_level="none",
                        categories=["citation_integrity"],
                        action="allow",
                        rationale_codes=[f"citation_stripped:{r.strip_reason}"],
                    ),
                    model_version,
                )

        # ------------------------------------------------------------------
        # 6. Post-check (on generated reflection)
        # ------------------------------------------------------------------
        post_result = classifier.classify(reflection)
        if post_result.action in ("refuse", "escalate"):
            await _log_safety_event(
                db, assistant_message_id, "post", post_result, model_version
            )
            ctx.warning("pipeline.post_check_triggered", action=post_result.action)
            if post_result.action == "escalate":
                await _emit_risk_interrupt(queue, post_result)
            else:
                await _emit_stream_error(
                    queue,
                    code="refused",
                    message="Response could not be delivered.",
                    retryable=False,
                )
            return

        # ------------------------------------------------------------------
        # 7. Emit stream
        # ------------------------------------------------------------------
        citation_payloads = _build_citation_payloads(validated_citations)
        full_text = await _emit_tokens(
            queue,
            message_id=assistant_message_id,
            text=reflection,
        )

        final = MessageFinalPayload(
            message_id=assistant_message_id,
            session_id=session_id,
            text=full_text,
            structured=StructuredPayload(
                reflection=reflection,
                prayer=prayer,
                next_step=next_step,
                reflection_question=reflection_question,
            ),
            citations=citation_payloads,
            risk=RiskPayload(
                risk_level=pre_result.risk_level,
                categories=pre_result.categories,
                action=pre_result.action,
            ),
            model_version=model_version,
            created_at=datetime.now(tz=timezone.utc),
        )
        await queue.put(_sse("message.final", final.model_dump(mode="json")))

        # Persist assistant message content
        await _persist_assistant_message(
            db,
            assistant_message_id=assistant_message_id,
            user_id=user_id,
            reflection=reflection,
            citation_results=citation_results,
            model_version=model_version,
        )
        await db.commit()
        ctx.info("pipeline.complete")

    except Exception as exc:  # noqa: BLE001
        ctx.exception("pipeline.unhandled_error", error=str(exc))
        await _emit_stream_error(
            queue,
            code="internal_error",
            message="An unexpected error occurred.",
            retryable=True,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_llm_output(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM output is not valid JSON: {exc}") from exc

    if not isinstance(data.get("reflection"), str) or not data["reflection"].strip():
        raise ValueError("LLM output missing required 'reflection' field")

    return data


async def _run_citation_gate(
    verse_block: list[dict],
    db: AsyncSession,
    ctx: Any,
) -> list[CitationResult]:
    try:
        return await validate_citations(verse_block, db)
    except Exception as exc:  # noqa: BLE001
        ctx.warning("pipeline.citation_gate_error", error=str(exc))
        return []


def _build_citation_payloads(
    validated: list[CitationResult],
) -> list[CitationPayload]:
    payloads = []
    for r in validated:
        entry = r.verse_block_entry
        payloads.append(
            CitationPayload(
                translation_id=entry.get("translation_id", ""),
                book=entry.get("book", ""),
                chapter=entry.get("chapter", 0),
                verse_start=entry.get("verse_start", 0),
                verse_end=entry.get("verse_end", entry.get("verse_start", 0)),
                verse_id_list=r.verse_id_list,
                quote=r.quote,
            )
        )
    return payloads


async def _emit_tokens(
    queue: asyncio.Queue,
    message_id: uuid.UUID,
    text: str,
) -> str:
    """Split text into word-sized chunks, emit token.delta events, return full text."""
    words = text.split(" ")
    parts: list[str] = []
    for i, word in enumerate(words):
        delta = word + (" " if i < len(words) - 1 else "")
        parts.append(delta)
        payload = TokenDeltaPayload(
            message_id=message_id,
            delta=delta,
            sequence=i + 1,
        )
        await queue.put(_sse("token.delta", payload.model_dump(mode="json")))
        await asyncio.sleep(0)  # yield control; no artificial delay in tests

    return "".join(parts)


async def _emit_risk_interrupt(
    queue: asyncio.Queue,
    result: SafetyCheckResult,
) -> None:
    payload = RiskInterruptPayload(
        risk_level=result.risk_level,
        action="escalate",
        categories=result.categories,
        message=CRISIS_TEMPLATE_PLACEHOLDER,
        resources=[ResourceItem(**r) for r in CRISIS_RESOURCES],
        requires_acknowledgment=True,
    )
    await queue.put(_sse("risk.interrupt", payload.model_dump(mode="json")))


async def _emit_stream_error(
    queue: asyncio.Queue,
    code: str,
    message: str,
    retryable: bool,
) -> None:
    payload = StreamErrorPayload(code=code, message=message, retryable=retryable)
    await queue.put(_sse("stream.error", payload.model_dump(mode="json")))


async def _log_safety_event(
    db: AsyncSession,
    message_id: uuid.UUID,
    check_stage: str,
    result: SafetyCheckResult,
    model_version: str,
) -> None:
    # Only log if risk > none OR categories are non-empty
    if result.risk_level == "none" and not result.categories:
        return
    event = SafetyEvent(
        message_id=message_id,
        check_stage=check_stage,
        risk_level=result.risk_level,
        categories=result.categories,
        action=result.action,
        rationale_codes=result.rationale_codes or [],
        model_version=model_version,
    )
    db.add(event)
    await db.flush()


async def _update_user_message(
    db: AsyncSession,
    user_message_id: uuid.UUID,
    content_encrypted: bytes,
    text_hash: str,
) -> None:
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(Message)
        .where(Message.id == user_message_id)
        .values(content_encrypted=content_encrypted, text_hash=text_hash)
    )
    await db.flush()


async def _persist_assistant_message(
    db: AsyncSession,
    assistant_message_id: uuid.UUID,
    user_id: uuid.UUID,
    reflection: str,
    citation_results: list[CitationResult],
    model_version: str,
) -> None:
    """Update the pre-allocated assistant message row and insert verse_citations."""
    from sqlalchemy import update as sa_update

    encrypted = message_crypto.encrypt(user_id, reflection)
    text_hash = hashlib.sha256(reflection.encode()).hexdigest()

    await db.execute(
        sa_update(Message)
        .where(Message.id == assistant_message_id)
        .values(
            content_encrypted=encrypted,
            text_hash=text_hash,
            model_version=model_version,
        )
    )
    await db.flush()

    for r in citation_results:
        if not r.validated:
            continue
        entry = r.verse_block_entry
        citation = VerseCitation(
            message_id=assistant_message_id,
            translation_id=entry.get("translation_id", ""),
            book=entry.get("book", ""),
            chapter=entry.get("chapter", 0),
            verse_start=entry.get("verse_start", 0),
            verse_end=entry.get("verse_end", entry.get("verse_start", 0)),
            verse_id_list=r.verse_id_list,
            validated=True,
        )
        db.add(citation)
    await db.flush()
