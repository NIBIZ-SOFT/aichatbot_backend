import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.models.all_models import PricingPlan, Coupon, CouponRedemption

logger = logging.getLogger(__name__)

DEFAULT_PLANS = [
    {
        "code": "free",
        "name": "Free Plan",
        "description": "Essential AI Chatbot widget for testing and early validation.",
        "badge_text": "Free Forever",
        "monthly_price_bdt": 0.0,
        "annual_price_bdt": 0.0,
        "monthly_token_limit": 50_000,
        "max_agents": 1,
        "max_websites": 1,
        "max_knowledge_docs": 2,
        "monthly_conversation_limit": 50,
        "features": [
            "50,000 AI Tokens / month",
            "1 Active Website Widget",
            "1 Staff / Agent Seat",
            "2 Knowledge Base Documents",
            "Standard AI Response Speed",
            "Community Support"
        ],
        "is_popular": False,
        "is_active": True,
        "is_custom_offer": False,
        "display_order": 1
    },
    {
        "code": "starter",
        "name": "Starter Plan",
        "description": "Professional conversational AI for growing e-commerce businesses.",
        "badge_text": "Starter",
        "monthly_price_bdt": 4990.0,
        "annual_price_bdt": 4240.0,
        "monthly_token_limit": 500_000,
        "max_agents": 2,
        "max_websites": 2,
        "max_knowledge_docs": 10,
        "monthly_conversation_limit": 200,
        "features": [
            "500,000 AI Tokens / month",
            "2 Active Website Widgets",
            "2 Staff / Agent Seats",
            "10 Knowledge Base Documents",
            "bKash & EPS Automated Billing",
            "Basic CSAT & Analytics",
            "Email Support (24h SLA)"
        ],
        "is_popular": False,
        "is_active": True,
        "is_custom_offer": False,
        "display_order": 2
    },
    {
        "code": "growth",
        "name": "Growth Plan",
        "description": "High-volume AI automation for scaling digital commerce brands.",
        "badge_text": "Most Popular",
        "monthly_price_bdt": 19990.0,
        "annual_price_bdt": 16990.0,
        "monthly_token_limit": 2_500_000,
        "max_agents": 5,
        "max_websites": 5,
        "max_knowledge_docs": 50,
        "monthly_conversation_limit": 1000,
        "features": [
            "2,500,000 AI Tokens / month",
            "5 Active Website Widgets",
            "5 Staff / Agent Seats",
            "50 Knowledge Base Documents",
            "E-Commerce Cart & Order Desk",
            "Advanced CSAT & Real-Time Analytics",
            "Custom Brand White-Labeling",
            "Priority WhatsApp & Ticket Support"
        ],
        "is_popular": True,
        "is_active": True,
        "is_custom_offer": False,
        "display_order": 3
    },
    {
        "code": "enterprise",
        "name": "Enterprise Plan",
        "description": "Dedicated LLM infrastructure, custom integrations & unlimited scalability.",
        "badge_text": "Enterprise",
        "monthly_price_bdt": 49990.0,
        "annual_price_bdt": 42490.0,
        "monthly_token_limit": 10_000_000,
        "max_agents": 20,
        "max_websites": 20,
        "max_knowledge_docs": 200,
        "monthly_conversation_limit": 5000,
        "features": [
            "10,000,000 AI Tokens / month",
            "20 Active Website Widgets",
            "20 Staff / Agent Seats",
            "200 Knowledge Base Documents",
            "Custom AI LLM Fine-Tuning & RAG",
            "Dedicated Account Manager",
            "Enterprise 99.9% SLA Guarantee",
            "24/7 Phone & Slack Direct Support"
        ],
        "is_popular": False,
        "is_active": True,
        "is_custom_offer": False,
        "display_order": 4
    }
]

class PricingService:
    @staticmethod
    async def seed_default_plans_if_empty(db: AsyncSession):
        stmt = select(PricingPlan)
        existing = (await db.execute(stmt)).scalars().first()
        if not existing:
            logger.info("Seeding default pricing plans into database...")
            for p in DEFAULT_PLANS:
                plan = PricingPlan(**p)
                db.add(plan)
            await db.commit()

    @staticmethod
    async def get_public_plans(db: AsyncSession) -> List[PricingPlan]:
        await PricingService.seed_default_plans_if_empty(db)
        now = datetime.now(timezone.utc)
        stmt = (
            select(PricingPlan)
            .where(PricingPlan.is_active == True)
            .order_by(PricingPlan.display_order.asc(), PricingPlan.monthly_price_bdt.asc())
        )
        res = await db.execute(stmt)
        plans = res.scalars().all()
        
        # Filter out expired custom offers
        valid_plans = []
        for p in plans:
            if p.valid_until and p.valid_until < now:
                continue
            valid_plans.append(p)
        return valid_plans

    @staticmethod
    async def get_all_plans(db: AsyncSession) -> List[PricingPlan]:
        await PricingService.seed_default_plans_if_empty(db)
        stmt = select(PricingPlan).order_by(PricingPlan.display_order.asc())
        res = await db.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def get_plan_by_code(db: AsyncSession, code: str) -> Optional[PricingPlan]:
        stmt = select(PricingPlan).where(PricingPlan.code == code.lower())
        return (await db.execute(stmt)).scalars().first()

    @staticmethod
    async def validate_coupon(
        db: AsyncSession,
        code: str,
        plan_code: str,
        amount_bdt: float
    ) -> Dict[str, Any]:
        """
        Validates coupon code against dates, usage limits, minimum purchase, and tier restrictions.
        """
        clean_code = code.strip().upper()
        stmt = select(Coupon).where(Coupon.code == clean_code, Coupon.is_active == True)
        coupon = (await db.execute(stmt)).scalars().first()

        if not coupon:
            return {
                "valid": False,
                "message": f"Coupon code '{clean_code}' is invalid or expired."
            }

        now = datetime.now(timezone.utc)

        # Check date validity
        if coupon.valid_until and coupon.valid_until < now:
            return {
                "valid": False,
                "message": f"Coupon code '{clean_code}' has expired."
            }

        # Check redemption limit
        if coupon.max_redemptions and coupon.redeemed_count >= coupon.max_redemptions:
            return {
                "valid": False,
                "message": f"Coupon code '{clean_code}' has reached its maximum usage limit."
            }

        # Check minimum purchase amount
        if amount_bdt < coupon.min_purchase_amount_bdt:
            return {
                "valid": False,
                "message": f"Minimum purchase amount of ৳{coupon.min_purchase_amount_bdt:,.0f} BDT required for coupon '{clean_code}'."
            }

        # Check tier restrictions
        if coupon.applicable_tiers and len(coupon.applicable_tiers) > 0:
            if plan_code.lower() not in [t.lower() for t in coupon.applicable_tiers]:
                return {
                    "valid": False,
                    "message": f"Coupon '{clean_code}' is only applicable for: {', '.join(coupon.applicable_tiers)}."
                }

        # Calculate discount
        if coupon.discount_type == "percentage":
            discount = (amount_bdt * coupon.discount_value) / 100.0
            if coupon.max_discount_amount_bdt and discount > coupon.max_discount_amount_bdt:
                discount = coupon.max_discount_amount_bdt
        else: # fixed_amount
            discount = coupon.discount_value

        discount = min(discount, amount_bdt) # cannot exceed total amount
        final_amount = max(0.0, amount_bdt - discount)

        return {
            "valid": True,
            "coupon_id": str(coupon.id),
            "code": coupon.code,
            "description": coupon.description,
            "discount_type": coupon.discount_type,
            "discount_value": coupon.discount_value,
            "discount_amount_bdt": round(discount, 2),
            "original_amount_bdt": round(amount_bdt, 2),
            "final_amount_bdt": round(final_amount, 2),
            "message": f"Coupon '{coupon.code}' applied successfully! You saved ৳{discount:,.0f} BDT."
        }

    @staticmethod
    async def redeem_coupon(
        db: AsyncSession,
        coupon_id: uuid.UUID,
        user_email: str,
        invoice_number: str,
        original_amount: float,
        discount_amount: float,
        final_amount: float,
        tenant_id: Optional[uuid.UUID] = None
    ) -> CouponRedemption:
        stmt = select(Coupon).where(Coupon.id == coupon_id)
        coupon = (await db.execute(stmt)).scalars().first()
        if coupon:
            coupon.redeemed_count += 1

        redemption = CouponRedemption(
            coupon_id=coupon_id,
            tenant_id=tenant_id,
            user_email=user_email,
            invoice_number=invoice_number,
            original_amount_bdt=original_amount,
            discount_applied_bdt=discount_amount,
            final_paid_amount_bdt=final_amount
        )
        db.add(redemption)
        await db.commit()
        return redemption

    @staticmethod
    async def get_pricing_engine_config(db: AsyncSession) -> Dict[str, Any]:
        """
        Retrieves global dynamic token pricing and PAYG master switch configuration.
        """
        from app.models.all_models import PlatformSetting
        stmt = select(PlatformSetting).where(PlatformSetting.key == "pricing_engine_config")
        setting = (await db.execute(stmt)).scalars().first()
        
        default_config = {
            "default_per_10k_tokens_rate_bdt": 1.50,
            "pay_as_you_go_enabled": True,
            "custom_slider_builder_enabled": True,
            "min_wallet_topup_bdt": 100.0,
            "annual_discount_percentage": 15.0,
            "base_custom_platform_fee_bdt": 1990.0,
            "per_extra_agent_bdt": 750.0,
            "per_extra_website_bdt": 1200.0
        }
        
        if not setting:
            return default_config
            
        merged = {**default_config, **(setting.value_json or {})}
        return merged

    @staticmethod
    async def update_pricing_engine_config(db: AsyncSession, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Updates global dynamic token pricing and PAYG switches in PlatformSetting.
        """
        from app.models.all_models import PlatformSetting
        from sqlalchemy.orm.attributes import flag_modified
        stmt = select(PlatformSetting).where(PlatformSetting.key == "pricing_engine_config")
        setting = (await db.execute(stmt)).scalars().first()
        
        if not setting:
            setting = PlatformSetting(
                key="pricing_engine_config",
                value_json=dict(config_data)
            )
            db.add(setting)
        else:
            current = dict(setting.value_json or {})
            current.update(config_data)
            setting.value_json = dict(current)
            flag_modified(setting, "value_json")
            setting.updated_at = datetime.now(timezone.utc)
            
        await db.commit()
        await db.refresh(setting)
        return setting.value_json

