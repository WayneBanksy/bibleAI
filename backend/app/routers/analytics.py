"""
POST /v1/analytics/event + GET /v1/analytics/summary — P1-05.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.config import Settings, settings as default_settings
from app.database import get_db
from app.services.analytics import get_summary, record_event

router = APIRouter()


class AnalyticsEventRequest(BaseModel):
    event_name: str
    timestamp: str
    session_id: str | None = None
    properties: dict = {}


def _settings() -> Settings:
    return default_settings


@router.post("/analytics/event", status_code=202)
async def ingest_event(
    request: AnalyticsEventRequest,
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        session_uuid = uuid.UUID(request.session_id) if request.session_id else None
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid session_id UUID")

    try:
        await record_event(user_id, request.event_name, session_uuid, request.properties, db)
        await db.commit()
        return {"accepted": True}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/analytics/summary")
async def summary(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_settings),
    _user_id=Depends(get_current_user_id),
):
    if not settings.is_dev:
        raise HTTPException(status_code=404)
    result = await get_summary(db)
    return result
