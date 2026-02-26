"""
GET /v1/entitlements — P1-01.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.config import Settings, settings as default_settings
from app.database import get_db
from app.models import User
from app.services.entitlements import get_entitlements

router = APIRouter()


def _settings() -> Settings:
    return default_settings


@router.get("/entitlements")
async def get_user_entitlements(
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_settings),
):
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
    snapshot = await get_entitlements(user, db, settings)
    await db.commit()  # persist any window reset
    return {"entitlements": snapshot}
