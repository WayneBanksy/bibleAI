"""
POST /v1/auth/token

Apple ID token exchange is STUBBED in development mode:
  - Accepts any id_token string as a fake Apple sub.
  - Creates (or retrieves) a User row keyed by that id_token.
  - Returns a short-lived JWT.

In production, replace _verify_apple_token with real Apple public-key validation.
"""
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token
from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import TokenRequest, TokenResponse

log = structlog.get_logger()
router = APIRouter()


async def _get_or_create_user(external_id: str, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.external_id == external_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(external_id=external_id)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        log.info("user.created", user_id=str(user.id))
    return user


@router.post("/token", response_model=TokenResponse)
async def exchange_token(
    body: TokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    if not settings.is_dev:
        # TODO: validate Apple id_token against Apple's public keys
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={"code": "not_implemented", "message": "Apple Sign-In verification not yet wired."},
        )

    # Dev stub: use the raw id_token string as external_id
    user = await _get_or_create_user(body.id_token, db)
    token = create_access_token(user.id)
    log.info("auth.token_issued", user_id=str(user.id))
    return TokenResponse(access_token=token, expires_in=settings.jwt_expiry_seconds)
