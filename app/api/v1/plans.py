import uuid
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.billing.pricing_service import PricingService

router = APIRouter(prefix="/plans", tags=["Pricing Plans & Coupons"])

class PublicPlanItem(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str
    badge_text: Optional[str] = None
    monthly_price_bdt: float
    annual_price_bdt: float
    monthly_token_limit: int
    max_agents: int
    max_websites: int
    max_knowledge_docs: int
    monthly_conversation_limit: int
    features: List[str]
    is_popular: bool
    is_custom_offer: bool
    display_order: int
    valid_until: Optional[datetime] = None

class ValidateCouponRequest(BaseModel):
    code: str = Field(..., description="Promo or coupon code")
    plan_code: str = Field(..., description="Plan code being purchased")
    amount_bdt: float = Field(..., description="Total purchase price in BDT")

class ValidateCouponResponse(BaseModel):
    valid: bool
    coupon_id: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[float] = None
    discount_amount_bdt: Optional[float] = None
    original_amount_bdt: Optional[float] = None
    final_amount_bdt: Optional[float] = None
    message: str

@router.get("/public", response_model=List[PublicPlanItem])
async def get_public_pricing_plans(db: AsyncSession = Depends(get_db)):
    """
    Publicly returns all active SaaS pricing tiers and special campaign offers.
    """
    plans = await PricingService.get_public_plans(db)
    return [
        PublicPlanItem(
            id=p.id,
            code=p.code,
            name=p.name,
            description=p.description,
            badge_text=p.badge_text,
            monthly_price_bdt=p.monthly_price_bdt,
            annual_price_bdt=p.annual_price_bdt,
            monthly_token_limit=p.monthly_token_limit,
            max_agents=p.max_agents,
            max_websites=p.max_websites,
            max_knowledge_docs=p.max_knowledge_docs,
            monthly_conversation_limit=p.monthly_conversation_limit,
            features=p.features or [],
            is_popular=p.is_popular,
            is_custom_offer=p.is_custom_offer,
            display_order=p.display_order,
            valid_until=p.valid_until
        )
        for p in plans
    ]

@router.post("/validate-coupon", response_model=ValidateCouponResponse)
async def validate_coupon_code(
    payload: ValidateCouponRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Validates a coupon code and calculates the discount amount.
    """
    result = await PricingService.validate_coupon(
        db=db,
        code=payload.code,
        plan_code=payload.plan_code,
        amount_bdt=payload.amount_bdt
    )
    return ValidateCouponResponse(**result)

@router.get("/config", response_model=dict)
async def get_public_pricing_config(db: AsyncSession = Depends(get_db)):
    """
    Returns public pricing configuration including PAYG status and default token rate.
    """
    config = await PricingService.get_pricing_engine_config(db)
    return config

@router.post("/custom-quote", response_model=dict)
async def get_custom_plan_quote(payload: dict, db: AsyncSession = Depends(get_db)):
    """
    Computes real-time dynamic pricing quote for interactive sliders & custom packages.
    """
    from app.services.billing.wallet_service import WalletService
    config = await PricingService.get_pricing_engine_config(db)
    token_rate = float(config.get("default_per_10k_tokens_rate_bdt", 1.50))
    annual_discount = float(config.get("annual_discount_percentage", 15.0))

    tokens = int(payload.get("tokens", 1_000_000))
    seats = int(payload.get("seats", 2))
    websites = int(payload.get("websites", 1))
    knowledge_docs = int(payload.get("knowledge_docs", 50))
    is_annual = bool(payload.get("is_annual", False))
    modules = payload.get("modules", {})
    
    quote = WalletService.calculate_custom_quote(
        tokens=tokens,
        seats=seats,
        websites=websites,
        knowledge_docs=knowledge_docs,
        is_annual=is_annual,
        modules=modules,
        token_rate_10k=token_rate,
        annual_discount_percent=annual_discount
    )
    return quote

