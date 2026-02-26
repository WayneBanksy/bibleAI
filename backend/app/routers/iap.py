"""
POST /v1/iap/verify  — verify IAP transaction (P1-04)
POST /v1/iap/sync    — re-validate subscription on app launch / restore
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.config import Settings, settings as default_settings
from app.database import get_db
from app.models import User
from app.schemas import IAPVerifyRequest, IAPVerifyResponse
from app.services.entitlements import get_entitlements
from app.services.iap_verification import verify_and_record
from app.services.subscription_sync import enforce_subscription_expiry

router = APIRouter()


def _settings() -> Settings:
    return default_settings


@router.post("/iap/verify", response_model=IAPVerifyResponse)
async def verify_iap_transaction(
    body: IAPVerifyRequest,
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_settings),
):
    """Verify a StoreKit 2 transaction and update entitlements."""
    try:
        result = await verify_and_record(
            user_id=user_id,
            platform=body.platform,
            product_type=body.product_type,
            product_id=body.product_id,
            transaction_id=body.transaction_id,
            original_transaction_id=body.original_transaction_id,
            environment=body.environment,
            signed_transaction_jws=body.signed_transaction_jws,
            signed_renewal_info_jws=body.signed_renewal_info_jws,
            db=db,
            settings=settings,
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_RECEIPT", "message": str(exc)}},
        )

    return result


@router.post("/iap/sync", response_model=IAPVerifyResponse)
async def sync_subscription(
    body: IAPVerifyRequest,
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(_settings),
):
    """
    Re-validate subscription on app launch / restore purchases.

    Same flow as /verify — idempotent. Also enforces expiry.
    """
    # Enforce expiry first
    user = (
        await db.execute(select(User).where(User.id == user_id).with_for_update())
    ).scalar_one()
    downgraded = enforce_subscription_expiry(user)
    if downgraded:
        await db.commit()

    try:
        result = await verify_and_record(
            user_id=user_id,
            platform=body.platform,
            product_type=body.product_type,
            product_id=body.product_id,
            transaction_id=body.transaction_id,
            original_transaction_id=body.original_transaction_id,
            environment=body.environment,
            signed_transaction_jws=body.signed_transaction_jws,
            signed_renewal_info_jws=body.signed_renewal_info_jws,
            db=db,
            settings=settings,
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_RECEIPT", "message": str(exc)}},
        )

    return result
