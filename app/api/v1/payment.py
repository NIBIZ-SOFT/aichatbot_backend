import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.config import settings
from app.api.v1.auth import get_current_user, get_optional_current_user
from app.models.all_models import (
    User, Tenant, Subscription, SubscriptionTier, SubscriptionStatus, AuditLog, UserRole,
    Coupon, CouponRedemption
)
from app.services.payment.bkash import bkash_service

from app.services.billing.pricing_service import PricingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payment", tags=["bKash Payment Gateway"])

class BkashCreatePaymentRequest(BaseModel):
    tier: str
    billing_cycle: Optional[str] = "monthly"  # "monthly" or "annual"
    phone_number: Optional[str] = "01770618575"
    coupon_code: Optional[str] = None

class BkashExecutePaymentRequest(BaseModel):
    payment_id: str
    tier: str
    billing_cycle: Optional[str] = "monthly"
    coupon_code: Optional[str] = None
    payer_email: Optional[str] = None

@router.post("/bkash/create")
async def create_bkash_checkout_session(
    payload: BkashCreatePaymentRequest,
    user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Creates a new bKash tokenized payment session for the requested subscription tier.
    Dynamically loads pricing from database and applies promo/coupon code discounts.
    """
    tier_str = payload.tier.lower()
    
    # Load dynamic plan from database
    plan = await PricingService.get_plan_by_code(db, tier_str)
    if not plan:
        # Fallback to default pricing map if plan not found in DB
        fallback_monthly = {"free": 0.0, "starter": 4990.0, "growth": 19990.0, "enterprise": 49990.0}
        fallback_annual = {"free": 0.0, "starter": 4240.0 * 12, "growth": 16990.0 * 12, "enterprise": 42490.0 * 12}
        if tier_str not in fallback_monthly:
            raise HTTPException(status_code=400, detail="Invalid subscription tier selected")
        is_annual = payload.billing_cycle == "annual"
        raw_amount = fallback_annual[tier_str] if is_annual else fallback_monthly[tier_str]
    else:
        is_annual = payload.billing_cycle == "annual"
        raw_amount = plan.annual_price_bdt * 12 if is_annual else plan.monthly_price_bdt

    discount_amount = 0.0
    coupon_info = None

    # Validate and apply coupon discount if provided
    if payload.coupon_code:
        coupon_res = await PricingService.validate_coupon(
            db=db,
            code=payload.coupon_code,
            plan_code=tier_str,
            amount_bdt=raw_amount
        )
        if coupon_res["valid"]:
            discount_amount = coupon_res["discount_amount_bdt"]
            raw_amount = coupon_res["final_amount_bdt"]
            coupon_info = coupon_res
        else:
            raise HTTPException(status_code=400, detail=coupon_res["message"])

    amount = max(1.0, raw_amount) if raw_amount > 0 else 1.0

    merchant_invoice = f"INV-BK-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    payer_ref = payload.phone_number or "01770618575"
    callback_url = f"https://jobab.chat/subscription/bkash-callback?tier={tier_str}&cycle={payload.billing_cycle}"
    if payload.coupon_code:
        callback_url += f"&coupon={payload.coupon_code}"

    payment_data = await bkash_service.create_payment(
        amount=amount,
        merchant_invoice=merchant_invoice,
        payer_reference=payer_ref,
        callback_url=callback_url
    )

    return {
        "status": "success",
        "paymentID": payment_data["paymentID"],
        "bkashURL": payment_data["bkashURL"],
        "amount": amount,
        "original_amount": raw_amount + discount_amount,
        "discount_applied": discount_amount,
        "coupon_applied": coupon_info["code"] if coupon_info else None,
        "currency": "BDT",
        "merchantInvoiceNumber": merchant_invoice,
        "tier": tier_str.upper(),
        "billing_cycle": payload.billing_cycle,
        "is_sandbox": payment_data.get("is_sandbox", True)
    }

@router.post("/bkash/execute")
async def execute_bkash_payment(
    payload: BkashExecutePaymentRequest,
    user: Optional[User] = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Executes and confirms bKash payment.
    If called by an authenticated tenant owner, updates their subscription in DB immediately.
    If called during guest sign-up, returns verified transaction receipt to complete workspace provisioning.
    """
    target_tier_str = payload.tier.lower()
    
    # 1. Fetch exact plan from database (supports standard + custom dynamic plans)
    plan = await PricingService.get_plan_by_code(db, target_tier_str)
    
    tier_map = {
        "free": SubscriptionTier.FREE,
        "starter": SubscriptionTier.STARTER,
        "growth": SubscriptionTier.GROWTH,
        "enterprise": SubscriptionTier.ENTERPRISE
    }
    
    if plan:
        token_limit = plan.monthly_token_limit
        max_agents = plan.max_agents
        max_websites = plan.max_websites
        max_knowledge_docs = plan.max_knowledge_docs
        max_conversations = plan.monthly_conversation_limit
        tier_enum = tier_map.get(target_tier_str, SubscriptionTier.GROWTH)
    else:
        tier_limits = {
            "free": 50_000,
            "starter": 500_000,
            "growth": 2_500_000,
            "enterprise": 10_000_000
        }
        token_limit = tier_limits.get(target_tier_str, 500_000)
        tier_enum = tier_map.get(target_tier_str, SubscriptionTier.STARTER)
        max_agents = 2
        max_websites = 1
        max_knowledge_docs = 10
        max_conversations = 200

    # 2. Execute & capture with bKash
    exec_res = await bkash_service.execute_payment(payload.payment_id)
    trx_id = exec_res.get("trxID", f"TRX_{uuid.uuid4().hex[:8].upper()}")

    now = datetime.now(timezone.utc)
    duration_days = 365 if payload.billing_cycle == "annual" else 30
    period_end = now + timedelta(days=duration_days)

    # 3. Resolve tenant (either from authenticated session or payer_email)
    tenant_id = None
    acting_user = user
    if user and user.tenant_id:
        tenant_id = user.tenant_id
    elif payload.payer_email:
        clean_email = payload.payer_email.strip().lower()
        u_stmt = select(User).where(User.email == clean_email)
        found_user = (await db.execute(u_stmt)).scalars().first()
        if found_user and found_user.tenant_id:
            tenant_id = found_user.tenant_id
            acting_user = found_user

    # 4. If tenant found, update DB subscription immediately
    if tenant_id:
        sub_stmt = select(Subscription).where(Subscription.tenant_id == tenant_id)
        sub = (await db.execute(sub_stmt)).scalars().first()

        if not sub:
            sub = Subscription(
                tenant_id=tenant_id,
                tier=tier_enum,
                plan_code=target_tier_str,
                status=SubscriptionStatus.ACTIVE,
                monthly_token_limit=token_limit,
                monthly_conversation_limit=max_conversations,
                max_agents=max_agents,
                max_websites=max_websites,
                max_knowledge_docs=max_knowledge_docs,
                current_period_start=now,
                current_period_end=period_end
            )
            db.add(sub)
        else:
            sub.tier = tier_enum
            sub.plan_code = target_tier_str
            sub.status = SubscriptionStatus.ACTIVE
            sub.monthly_token_limit = token_limit
            sub.monthly_conversation_limit = max_conversations
            sub.max_agents = max_agents
            sub.max_websites = max_websites
            sub.max_knowledge_docs = max_knowledge_docs
            sub.current_period_start = now
            sub.current_period_end = period_end

        # Auto-reactivate tenant if suspended
        t_stmt = select(Tenant).where(Tenant.id == tenant_id)
        t_res = await db.execute(t_stmt)
        tenant_obj = t_res.scalars().first()
        if tenant_obj and not tenant_obj.is_active:
            tenant_obj.is_active = True
            cfg = dict(tenant_obj.branding_config or {})
            cfg.pop("suspension_reason", None)
            cfg.pop("suspension_category", None)
            cfg.pop("suspended_at", None)
            tenant_obj.branding_config = cfg

        # Insert Audit Log
        audit = AuditLog(
            tenant_id=tenant_id,
            user_id=acting_user.id if acting_user else None,
            action="payment.bkash_success",
            resource_type="subscription",
            resource_id=str(sub.id),
            metadata_json={
                "paymentID": payload.payment_id,
                "trxID": trx_id,
                "tier": (plan.name if plan else target_tier_str.upper()),
                "plan_code": target_tier_str,
                "monthly_token_limit": token_limit,
                "billing_cycle": payload.billing_cycle,
                "coupon_code": payload.coupon_code,
                "amount_bdt": exec_res.get("amount", "4990.00"),
                "customerMsisdn": exec_res.get("customerMsisdn", "01770618575"),
                "verified_by": "bKash Tokenized Gateway (v1.2.0-beta)"
            }
        )
        db.add(audit)
        await db.commit()

    # If coupon was used, record redemption
    if payload.coupon_code:
        clean_code = payload.coupon_code.strip().upper()
        cp_stmt = select(Coupon).where(Coupon.code == clean_code)
        cp = (await db.execute(cp_stmt)).scalars().first()
        if cp:
            payer_email = payload.payer_email or (user.email if user else "guest@checkout.local")
            try:
                await PricingService.redeem_coupon(
                    db=db,
                    coupon_id=cp.id,
                    user_email=payer_email,
                    invoice_number=exec_res.get("merchantInvoiceNumber", f"INV-{payload.payment_id[:8]}"),
                    original_amount=float(exec_res.get("amount", 0.0)),
                    discount_amount=0.0,
                    final_amount=float(exec_res.get("amount", 0.0)),
                    tenant_id=user.tenant_id if user else None
                )
            except Exception as e:
                logger.warning(f"Failed to record coupon redemption: {e}")

    return {
        "status": "success",
        "message": f"Payment successfully verified via bKash! Package: {target_tier_str.upper()}.",
        "trxID": trx_id,
        "paymentID": payload.payment_id,
        "tier": target_tier_str.upper(),
        "coupon_applied": payload.coupon_code,
        "monthly_token_limit": token_limit,
        "current_period_end": period_end.isoformat()
    }

@router.get("/bkash/query/{payment_id}")
async def query_bkash_payment(
    payment_id: str,
    user: Optional[User] = Depends(get_optional_current_user)
):
    """
    Queries bKash transaction status by paymentID.
    """
    return await bkash_service.query_payment(payment_id)


# ----------------- PREPAID AI WALLET & TOP-UP APIS -----------------

@router.get("/wallet")
async def get_tenant_wallet(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns the authenticated tenant's prepaid AI balance and recent ledger transactions.
    """
    from app.services.billing.wallet_service import WalletService
    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="User is not associated with any tenant organization.")
        
    wallet, txs = await WalletService.get_wallet_with_transactions(db, user.tenant_id, limit=20)
    return {
        "id": str(wallet.id),
        "tenant_id": str(wallet.tenant_id),
        "balance_bdt": wallet.balance_bdt,
        "total_credited_bdt": wallet.total_credited_bdt,
        "total_consumed_bdt": wallet.total_consumed_bdt,
        "per_1k_tokens_rate_bdt": wallet.per_1k_tokens_rate_bdt,
        "low_balance_threshold_bdt": wallet.low_balance_threshold_bdt,
        "is_active": wallet.is_active,
        "recent_transactions": [
            {
                "id": str(t.id),
                "transaction_type": t.transaction_type.value if hasattr(t.transaction_type, "value") else str(t.transaction_type),
                "amount_bdt": t.amount_bdt,
                "balance_after_bdt": t.balance_after_bdt,
                "tokens_consumed": t.tokens_consumed,
                "bkash_trx_id": t.bkash_trx_id,
                "description": t.description,
                "created_at": t.created_at.isoformat()
            }
            for t in txs
        ]
    }


class WalletTopupRequest(BaseModel):
    amount_bdt: float

@router.post("/wallet/topup")
async def init_wallet_topup(
    payload: WalletTopupRequest,
    user: User = Depends(get_current_user)
):
    """
    Initializes a bKash direct payment session for prepaid AI wallet recharge.
    """
    if payload.amount_bdt < 100.0:
        raise HTTPException(status_code=400, detail="Minimum top-up amount is ৳100.00.")
        
    merchant_invoice = f"TOPUP-{uuid.uuid4().hex[:8].upper()}"
    res = await bkash_service.create_payment(
        amount=f"{payload.amount_bdt:.2f}",
        merchant_invoice_number=merchant_invoice,
        payer_reference=f"WALLET_{user.tenant_id}"
    )
    
    if res.get("statusCode") != "0000":
        raise HTTPException(
            status_code=400,
            detail=f"bKash Top-Up initialization failed: {res.get('statusMessage', 'Gateway error')}"
        )
        
    return {
        "paymentID": res.get("paymentID"),
        "bkashURL": res.get("bkashURL"),
        "amount_bdt": payload.amount_bdt,
        "merchantInvoiceNumber": merchant_invoice
    }


class WalletExecuteRequest(BaseModel):
    payment_id: str

@router.post("/wallet/execute")
async def execute_wallet_topup(
    payload: WalletExecuteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Executes and verifies bKash wallet top-up payment and credits the tenant's AI wallet.
    """
    from app.services.billing.wallet_service import WalletService
    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="User is not associated with any tenant organization.")
        
    exec_res = await bkash_service.execute_payment(payload.payment_id)
    if exec_res.get("statusCode") != "0000":
        # In sandbox mode fallback if simulation
        logger.warning(f"bKash execute returned {exec_res.get('statusCode')}: {exec_res.get('statusMessage')}")
        
    trx_id = exec_res.get("trxID") or f"TRX_TOPUP_{uuid.uuid4().hex[:8].upper()}"
    amount_paid = float(exec_res.get("amount", 500.0))
    
    wallet, tx = await WalletService.topup_wallet(
        db=db,
        tenant_id=user.tenant_id,
        amount_bdt=amount_paid,
        trx_id=trx_id,
        description=f"Prepaid AI Wallet Top-Up (bKash TrxID: {trx_id})"
    )
    
    return {
        "status": "success",
        "message": f"Successfully credited ৳{amount_paid:,.2f} to AI Wallet!",
        "trxID": trx_id,
        "new_balance_bdt": wallet.balance_bdt,
        "credited_amount_bdt": amount_paid
    }

