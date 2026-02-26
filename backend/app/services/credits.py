"""
Credit system service — P1-02.

Idempotent credit redemption + atomic credit consumption.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CreditLedger, User

# Server-authoritative product → quantity mapping.
CREDIT_PRODUCTS: dict[str, int] = {
    "credits_5": 5,
    "credits_10": 10,
    "credits_30": 30,
    "credits_50": 50,
}


async def redeem_credits(
    user_id: uuid.UUID,
    product_id: str,
    idempotency_key: str,
    db: AsyncSession,
) -> dict:
    """Redeem a credit pack. Idempotent on (user_id, idempotency_key)."""
    if product_id not in CREDIT_PRODUCTS:
        raise ValueError(f"Invalid product_id: {product_id}")

    quantity = CREDIT_PRODUCTS[product_id]

    ledger = CreditLedger(
        user_id=user_id,
        delta=quantity,
        reason="iap_redeem",
        idempotency_key=idempotency_key,
        product_id=product_id,
    )
    db.add(ledger)

    try:
        # Lock user row and update balance atomically
        user = (
            await db.execute(select(User).where(User.id == user_id).with_for_update())
        ).scalar_one()
        user.credits_balance += quantity
        await db.commit()
        return {"credits_balance": user.credits_balance, "added": quantity}
    except IntegrityError:
        await db.rollback()
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
        return {"credits_balance": user.credits_balance, "added": 0, "duplicate": True}


async def consume_credit_if_needed(
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    db: AsyncSession,
) -> bool:
    """Atomically consume 1 credit. Returns True if consumed, False if balance is 0."""
    result = await db.execute(
        update(User)
        .where(User.id == user_id, User.credits_balance > 0)
        .values(credits_balance=User.credits_balance - 1)
        .returning(User.credits_balance)
    )
    new_balance = result.scalar_one_or_none()

    if new_balance is None:
        return False

    ledger = CreditLedger(
        user_id=user_id,
        delta=-1,
        reason="session_consume",
        related_session_id=session_id,
    )
    db.add(ledger)
    await db.flush()
    return True
