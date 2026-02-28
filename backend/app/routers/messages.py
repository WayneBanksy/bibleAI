"""
POST /v1/sessions/{id}/messages  — send a user message (202, triggers demo stream)
GET  /v1/sessions/{id}/events    — SSE stream of events for this session
"""
import hashlib
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUserID
from app.database import get_db
from app.models import Message, Session
from app.schemas import (
    SendMessageAccepted,
    SendMessageRequest,
)
from app.streaming import publish_real_stream, sse_generator

log = structlog.get_logger()
router = APIRouter()


# ---------------------------------------------------------------------------
# POST /v1/sessions/{session_id}/messages
# ---------------------------------------------------------------------------

@router.post("/{session_id}/messages", status_code=status.HTTP_202_ACCEPTED, response_model=SendMessageAccepted)
async def send_message(
    session_id: uuid.UUID,
    body: SendMessageRequest,
    background_tasks: BackgroundTasks,
    user_id: CurrentUserID,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> SendMessageAccepted:
    session = await _get_owned_session(session_id, user_id, db)

    # Idempotency: check for existing message with same client_message_id
    existing = await _find_existing_message(session_id, body.client_message_id, db)
    if existing is not None:
        request_id = request.headers.get("X-Request-ID", "")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "conflict",
                "message": "Duplicate client_message_id for this session.",
                "request_id": request_id,
                "details": {
                    "original_message_id": str(existing.id),
                    "client_message_id": str(body.client_message_id),
                },
            },
        )

    # Persist user message (text stored only as hash; no plaintext per D008)
    text_hash = hashlib.sha256(body.text.encode()).hexdigest()
    user_msg = Message(
        session_id=session_id,
        role="user",
        text_hash=text_hash,
        client_message_id=body.client_message_id,
        msg_metadata={"input_mode": body.input_mode},
    )
    db.add(user_msg)

    # Pre-allocate assistant message ID so the client can correlate stream events
    assistant_msg_id = uuid.uuid4()
    assistant_msg = Message(
        id=assistant_msg_id,
        session_id=session_id,
        role="assistant",
        model_version="stub-v1",
    )
    db.add(assistant_msg)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Rare race condition: concurrent request with same client_message_id
        existing = await _find_existing_message(session_id, body.client_message_id, db)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "conflict",
                "message": "Duplicate client_message_id for this session.",
                "details": {"original_message_id": str(existing.id) if existing else None},
            },
        )

    log.info(
        "message.received",
        session_id=str(session_id),
        user_msg_id=str(user_msg.id),
        assistant_msg_id=str(assistant_msg_id),
        client_message_id=str(body.client_message_id),
    )

    # Kick off real pipeline in the background — returns 202 immediately
    background_tasks.add_task(
        publish_real_stream,
        str(session_id),
        user_id,
        user_msg.id,
        assistant_msg_id,
        body.text,
        db,
    )

    return SendMessageAccepted(
        message_id=assistant_msg_id,
        client_message_id=body.client_message_id,
        session_id=session_id,
    )


# ---------------------------------------------------------------------------
# GET /v1/sessions/{session_id}/events  (SSE)
# ---------------------------------------------------------------------------

@router.get("/{session_id}/events")
async def stream_events(
    session_id: uuid.UUID,
    user_id: CurrentUserID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    await _get_owned_session(session_id, user_id, db)

    log.info("sse.connected", session_id=str(session_id), user_id=str(user_id))

    return StreamingResponse(
        sse_generator(str(session_id)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_owned_session(
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> Session:
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.user_id == user_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Session not found."},
        )
    return session


async def _find_existing_message(
    session_id: uuid.UUID,
    client_message_id: uuid.UUID,
    db: AsyncSession,
) -> Message | None:
    result = await db.execute(
        select(Message).where(
            Message.session_id == session_id,
            Message.client_message_id == client_message_id,
            Message.role == "user",
        )
    )
    return result.scalar_one_or_none()
