"""
POST /v1/safety/report
"""
import hashlib

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUserID
from app.database import get_db
from app.models import Report, Session
from app.schemas import SafetyReportRequest, SafetyReportResponse
from typing import Annotated
import uuid

log = structlog.get_logger()
router = APIRouter()


@router.post("/report", status_code=status.HTTP_200_OK, response_model=SafetyReportResponse)
async def submit_safety_report(
    body: SafetyReportRequest,
    user_id: CurrentUserID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SafetyReportResponse:
    # Verify the session belongs to this user
    result = await db.execute(
        select(Session).where(Session.id == body.session_id, Session.user_id == user_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Session not found."},
        )

    details_hash = hashlib.sha256(body.details.encode()).hexdigest() if body.details else None
    report = Report(
        session_id=body.session_id,
        message_id=body.message_id,
        user_id=user_id,
        reason=body.reason,
        details_hash=details_hash,
    )
    db.add(report)
    await db.commit()
    log.info("report.submitted", report_id=str(report.id), reason=body.reason)
    return SafetyReportResponse(report_id=report.id)
