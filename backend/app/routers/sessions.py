"""
POST /v1/sessions      — create session
GET  /v1/sessions/{id} — get session detail
"""
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUserID
from app.database import get_db
from app.models import Message, Session
from app.schemas import CreateSessionRequest, SessionDetailResponse, SessionResponse

log = structlog.get_logger()
router = APIRouter()

_DEFAULT_TRANSLATION = "NIV"
_DEFAULT_TONE = "reflective"


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SessionResponse)
async def create_session(
    body: CreateSessionRequest,
    user_id: CurrentUserID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionResponse:
    session = Session(
        user_id=user_id,
        mode=body.mode,
        translation_preference=body.translation_preference or _DEFAULT_TRANSLATION,
        tone_preference=body.tone_preference or _DEFAULT_TONE,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    log.info("session.created", session_id=str(session.id), user_id=str(user_id), mode=body.mode)
    return SessionResponse(
        session_id=session.id,
        mode=session.mode,
        translation_preference=session.translation_preference,
        tone_preference=session.tone_preference,
        created_at=session.started_at,
    )


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: uuid.UUID,
    user_id: CurrentUserID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionDetailResponse:
    session = await _get_owned_session(session_id, user_id, db)

    count_result = await db.execute(
        select(func.count()).select_from(Message).where(Message.session_id == session_id)
    )
    message_count = count_result.scalar_one()

    # updated_at approximated by the latest message or session start
    latest_msg = await db.execute(
        select(Message.created_at)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    latest_ts = latest_msg.scalar_one_or_none()
    updated_at = latest_ts or session.started_at

    return SessionDetailResponse(
        session_id=session.id,
        mode=session.mode,
        status=session.status,
        message_count=message_count,
        created_at=session.started_at,
        updated_at=updated_at,
    )


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
