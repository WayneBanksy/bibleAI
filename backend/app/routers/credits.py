"""
POST /v1/credits/redeem — P1-02.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.database import get_db
from app.services.credits import CREDIT_PRODUCTS, redeem_credits

router = APIRouter()


class RedeemCreditsRequest(BaseModel):
    idempotency_key: str
    product_id: str
    purchase_token: str
    purchased_at: str


@router.post("/credits/redeem")
async def redeem(
    request: RedeemCreditsRequest,
    user_id=Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    if request.product_id not in CREDIT_PRODUCTS:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_PURCHASE", "message": f"Unknown product_id: {request.product_id}"}},
        )

    result = await redeem_credits(user_id, request.product_id, request.idempotency_key, db)

    if result.get("duplicate"):
        raise HTTPException(status_code=409, detail={"credits_balance": result["credits_balance"], "added": 0})

    return {"credits_balance": result["credits_balance"], "added": result["added"]}
