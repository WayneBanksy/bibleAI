"""
IAP transaction verification service — P1-04.

Pluggable verifier interface: DevStubVerifier for development, ProductionVerifier for Apple API.
"""
from __future__ import annotations

import abc
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import IAPTransaction, User
from app.services.entitlements import get_entitlements
from app.services.subscription_sync import sync_subscription_from_transaction

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Verified result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerifiedSubscription:
    transaction_id: str
    original_transaction_id: str | None
    product_id: str
    expires_at: datetime
    status: str  # "active" | "grace" | "billing_retry" | "expired"
    revocation_date: datetime | None = None
    environment: str = "Sandbox"


@dataclass(frozen=True)
class VerifiedConsumable:
    transaction_id: str
    product_id: str
    environment: str = "Sandbox"


# ---------------------------------------------------------------------------
# Verifier interface
# ---------------------------------------------------------------------------


class IAPVerifier(abc.ABC):
    @abc.abstractmethod
    async def verify_subscription(
        self,
        signed_transaction_jws: str | None,
        signed_renewal_info_jws: str | None,
        transaction_id: str,
        product_id: str,
    ) -> VerifiedSubscription: ...

    @abc.abstractmethod
    async def verify_consumable(
        self,
        signed_transaction_jws: str | None,
        transaction_id: str,
        product_id: str,
    ) -> VerifiedConsumable: ...


# ---------------------------------------------------------------------------
# DevStubVerifier — development only
# ---------------------------------------------------------------------------


class DevStubVerifier(IAPVerifier):
    """Accepts all payloads without cryptographic verification. DEV ONLY."""

    async def verify_subscription(
        self,
        signed_transaction_jws: str | None,
        signed_renewal_info_jws: str | None,
        transaction_id: str,
        product_id: str,
    ) -> VerifiedSubscription:
        return VerifiedSubscription(
            transaction_id=transaction_id,
            original_transaction_id=None,
            product_id=product_id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            status="active",
            environment="Sandbox",
        )

    async def verify_consumable(
        self,
        signed_transaction_jws: str | None,
        transaction_id: str,
        product_id: str,
    ) -> VerifiedConsumable:
        return VerifiedConsumable(
            transaction_id=transaction_id,
            product_id=product_id,
            environment="Sandbox",
        )


# ---------------------------------------------------------------------------
# ProductionVerifier — Apple App Store Server API (placeholder)
# ---------------------------------------------------------------------------


class ProductionVerifier(IAPVerifier):
    """
    Uses Apple App Store Server API to verify transactions.

    Requires:
      - APPLE_API_KEY_ID
      - APPLE_API_ISSUER_ID
      - APPLE_API_PRIVATE_KEY (PEM)

    TODO: Implement once Apple credentials are provisioned (B005-adjacent).
    """

    async def verify_subscription(
        self,
        signed_transaction_jws: str | None,
        signed_renewal_info_jws: str | None,
        transaction_id: str,
        product_id: str,
    ) -> VerifiedSubscription:
        raise NotImplementedError(
            "ProductionVerifier not yet implemented. "
            "Provision Apple API credentials and implement App Store Server API calls."
        )

    async def verify_consumable(
        self,
        signed_transaction_jws: str | None,
        transaction_id: str,
        product_id: str,
    ) -> VerifiedConsumable:
        raise NotImplementedError(
            "ProductionVerifier not yet implemented."
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_verifier(settings: Settings) -> IAPVerifier:
    if settings.is_dev:
        log.warning("IAP verification using DevStubVerifier — NOT for production use.")
        return DevStubVerifier()
    return ProductionVerifier()


# ---------------------------------------------------------------------------
# Verify endpoint logic
# ---------------------------------------------------------------------------


async def verify_and_record(
    user_id: uuid.UUID,
    platform: str,
    product_type: str,
    product_id: str,
    transaction_id: str,
    original_transaction_id: str | None,
    environment: str,
    signed_transaction_jws: str | None,
    signed_renewal_info_jws: str | None,
    db: AsyncSession,
    settings: Settings,
) -> dict:
    """
    Verify an IAP transaction and record it. Returns entitlements snapshot.

    Idempotent: if (platform, transaction_id) already exists, returns current entitlements.
    """
    # Check idempotency — already recorded?
    existing = (
        await db.execute(
            select(IAPTransaction).where(
                IAPTransaction.platform == platform,
                IAPTransaction.transaction_id == transaction_id,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
        snapshot = await get_entitlements(user, db, settings)
        return {"entitlements": snapshot, "verified": True, "already_recorded": True}

    # Verify with the pluggable verifier
    verifier = get_verifier(settings)

    expires_at: datetime | None = None
    revocation_date: datetime | None = None

    if product_type == "subscription":
        result = await verifier.verify_subscription(
            signed_transaction_jws=signed_transaction_jws,
            signed_renewal_info_jws=signed_renewal_info_jws,
            transaction_id=transaction_id,
            product_id=product_id,
        )
        expires_at = result.expires_at
        revocation_date = result.revocation_date
        environment = result.environment
    else:
        result = await verifier.verify_consumable(
            signed_transaction_jws=signed_transaction_jws,
            transaction_id=transaction_id,
            product_id=product_id,
        )
        environment = result.environment

    # Record transaction
    txn = IAPTransaction(
        user_id=user_id,
        platform=platform,
        transaction_id=transaction_id,
        original_transaction_id=original_transaction_id,
        product_id=product_id,
        product_type=product_type,
        signed_transaction_jws=None,  # Never persist raw JWS for privacy
        signed_renewal_info_jws=None,
        expires_at=expires_at,
        revocation_date=revocation_date,
        environment=environment,
    )
    db.add(txn)

    try:
        await db.flush()
    except IntegrityError:
        # Race condition: another request recorded the same transaction
        await db.rollback()
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
        snapshot = await get_entitlements(user, db, settings)
        return {"entitlements": snapshot, "verified": True, "already_recorded": True}

    # Update subscription state if this is a subscription purchase
    user = (
        await db.execute(select(User).where(User.id == user_id).with_for_update())
    ).scalar_one()

    if product_type == "subscription":
        sync_subscription_from_transaction(user, expires_at, revocation_date)

    await db.commit()

    snapshot = await get_entitlements(user, db, settings)
    return {"entitlements": snapshot, "verified": True}
