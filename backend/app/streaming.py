"""
In-memory SSE event queue per session.

Architecture: asyncio.Queue per session_id, keyed by string.
Scope: single-instance only (MVP). For multi-instance, replace with
       Redis Streams or a similar pub/sub backend.

Usage:
  - Message handler puts formatted SSE strings into the queue.
  - SSE endpoint consumes from the queue, yielding heartbeats on timeout.
"""
import asyncio
import json
import uuid
from collections import defaultdict
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from app.schemas import MessageFinalPayload, RiskPayload, StructuredPayload, TokenDeltaPayload

# Global registry: session_id (str) → asyncio.Queue[str | None]
# None is the sentinel that signals the generator to stop.
_queues: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)

HEARTBEAT_INTERVAL_SECONDS = 15
DEMO_TOKENS = (
    "This is a demo response showing how streaming works. "
    "In production the LLM generates this text token by token, "
    "grounded in validated scripture from the verse corpus."
).split()


def _queue(session_id: str) -> asyncio.Queue:
    return _queues[session_id]


def _sse(event: str, data: str | dict) -> str:
    payload = json.dumps(data) if isinstance(data, dict) else data
    return f"event: {event}\ndata: {payload}\n\n"


async def publish_real_stream(
    session_id: str,
    user_id: uuid.UUID,
    user_message_id: uuid.UUID,
    assistant_message_id: uuid.UUID,
    text: str,
    db,  # AsyncSession — imported lazily to avoid circular import
    translation_preference: str = "KJV",
    session_mode: str = "support_session",
) -> None:
    """
    Background task: run the real pipeline and stream events into the session queue.
    Called after POST /v1/sessions/{id}/messages returns 202.
    """
    from app.pipeline import run_pipeline  # lazy import to avoid circular

    q = _queue(session_id)
    await run_pipeline(
        session_id=uuid.UUID(session_id),
        user_id=user_id,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        text=text,
        db=db,
        queue=q,
        translation_preference=translation_preference,
        session_mode=session_mode,
    )


async def publish_demo_stream(session_id: str, message_id: uuid.UUID) -> None:
    """
    Background task: emit token.delta events then a message.final event.
    Called after POST /v1/sessions/{id}/messages returns 202.
    """
    q = _queue(session_id)
    full_text_parts: list[str] = []

    for i, word in enumerate(DEMO_TOKENS):
        delta = word + (" " if i < len(DEMO_TOKENS) - 1 else "")
        full_text_parts.append(delta)
        payload = TokenDeltaPayload(
            message_id=message_id,
            delta=delta,
            sequence=i + 1,
        )
        await q.put(_sse("token.delta", payload.model_dump(mode="json")))
        await asyncio.sleep(0.04)  # ~25 tokens/sec for demo feel

    full_text = "".join(full_text_parts)
    final = MessageFinalPayload(
        message_id=message_id,
        session_id=uuid.UUID(session_id),
        text=full_text,
        structured=StructuredPayload(
            reflection=full_text,
            prayer=None,
            next_step="Take a moment to sit with this reflection.",
            reflection_question="What does this bring up for you?",
        ),
        citations=[],
        risk=RiskPayload(risk_level="none", categories=[], action="allow"),
        model_version="demo-stub-v0",
        created_at=datetime.now(tz=timezone.utc),
    )
    await q.put(_sse("message.final", final.model_dump(mode="json")))


async def sse_generator(session_id: str) -> AsyncGenerator[str, None]:
    """
    Async generator consumed by the SSE StreamingResponse.
    Yields heartbeats every HEARTBEAT_INTERVAL_SECONDS while waiting for events.
    """
    q = _queue(session_id)
    while True:
        try:
            event = await asyncio.wait_for(q.get(), timeout=float(HEARTBEAT_INTERVAL_SECONDS))
            if event is None:  # sentinel — stream closed
                return
            yield event
        except asyncio.TimeoutError:
            yield _sse("heartbeat", {})
