import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.models.all_models import TenantWallet, WalletTransaction, WalletTransactionType, Tenant

logger = logging.getLogger(__name__)

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class WalletService:
    @staticmethod
    async def get_or_create_wallet(db: AsyncSession, tenant_id: uuid.UUID) -> TenantWallet:
        """
        Retrieves the tenant's prepaid AI wallet, or creates a new one with 0 balance if absent.
        """
        stmt = select(TenantWallet).where(TenantWallet.tenant_id == tenant_id)
        wallet = (await db.execute(stmt)).scalars().first()
        
        if not wallet:
            from app.services.billing.pricing_service import PricingService
            p_config = await PricingService.get_pricing_engine_config(db)
            default_per_10k = float(p_config.get("default_per_10k_tokens_rate_bdt", 1.50))
            per_1k_rate = round(default_per_10k / 10.0, 4)
            
            wallet = TenantWallet(
                tenant_id=tenant_id,
                balance_bdt=0.0,
                total_credited_bdt=0.0,
                total_consumed_bdt=0.0,
                per_1k_tokens_rate_bdt=per_1k_rate,
                low_balance_threshold_bdt=50.0,
                is_custom_rate=False,
                is_active=True
            )
            db.add(wallet)
            await db.commit()
            await db.refresh(wallet)
            logger.info(f"Initialized new TenantWallet for tenant {tenant_id} at ৳{per_1k_rate}/1k tokens")
            
        return wallet

    @staticmethod
    async def get_wallet_with_transactions(db: AsyncSession, tenant_id: uuid.UUID, limit: int = 15) -> Tuple[TenantWallet, List[WalletTransaction]]:
        wallet = await WalletService.get_or_create_wallet(db, tenant_id)
        
        stmt = (
            select(WalletTransaction)
            .where(WalletTransaction.wallet_id == wallet.id)
            .order_by(desc(WalletTransaction.created_at))
            .limit(limit)
        )
        txs = (await db.execute(stmt)).scalars().all()
        return wallet, list(txs)

    @staticmethod
    async def topup_wallet(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        amount_bdt: float,
        payment_id: Optional[uuid.UUID] = None,
        trx_id: Optional[str] = None,
        description: str = "Prepaid AI Wallet Top-Up via bKash"
    ) -> Tuple[TenantWallet, WalletTransaction]:
        """
        Credits the tenant's wallet and records the ledger transaction.
        """
        wallet = await WalletService.get_or_create_wallet(db, tenant_id)
        
        wallet.balance_bdt += amount_bdt
        wallet.total_credited_bdt += amount_bdt
        wallet.updated_at = utc_now()
        
        tx = WalletTransaction(
            wallet_id=wallet.id,
            tenant_id=tenant_id,
            transaction_type=WalletTransactionType.TOPUP,
            amount_bdt=amount_bdt,
            balance_after_bdt=wallet.balance_bdt,
            tokens_consumed=0,
            payment_id=payment_id,
            bkash_trx_id=trx_id,
            description=description,
            metadata_json={
                "source": "bKash Direct Gateway",
                "trx_id": trx_id,
                "topup_at": utc_now().isoformat()
            }
        )
        db.add(tx)
        await db.commit()
        await db.refresh(wallet)
        await db.refresh(tx)
        
        logger.info(f"Credited ৳{amount_bdt} to tenant {tenant_id} wallet (TrxID: {trx_id}). New balance: ৳{wallet.balance_bdt}")
        return wallet, tx

    @staticmethod
    async def deduct_usage(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        tokens_consumed: int,
        conversation_id: Optional[uuid.UUID] = None,
        description: str = "AI Model Telemetry Token Usage"
    ) -> Optional[WalletTransaction]:
        """
        Deducts micro-BDT from the tenant wallet based on token consumption.
        """
        if tokens_consumed <= 0:
            return None
            
        wallet = await WalletService.get_or_create_wallet(db, tenant_id)
        
        # Calculate cost based on per 1k token rate
        cost_bdt = (tokens_consumed / 1000.0) * wallet.per_1k_tokens_rate_bdt
        cost_bdt = round(cost_bdt, 4)
        
        wallet.balance_bdt = max(0.0, wallet.balance_bdt - cost_bdt)
        wallet.total_consumed_bdt += cost_bdt
        wallet.updated_at = utc_now()
        
        tx = WalletTransaction(
            wallet_id=wallet.id,
            tenant_id=tenant_id,
            transaction_type=WalletTransactionType.USAGE_AI_TOKENS,
            amount_bdt=-cost_bdt,
            balance_after_bdt=wallet.balance_bdt,
            tokens_consumed=tokens_consumed,
            description=description,
            metadata_json={
                "tokens": tokens_consumed,
                "cost_bdt": cost_bdt,
                "conversation_id": str(conversation_id) if conversation_id else None
            }
        )
        db.add(tx)
        await db.commit()
        await db.refresh(wallet)
        await db.refresh(tx)
        
        return tx

    @staticmethod
    def calculate_custom_quote(
        tokens: int = 1_000_000,
        seats: int = 2,
        websites: int = 1,
        knowledge_docs: int = 50,
        is_annual: bool = False,
        modules: Optional[Dict[str, bool]] = None
    ) -> Dict[str, Any]:
        """
        Calculates reactive custom plan quote in Bangladeshi Taka based on selected resources.
        """
        base_platform_fee = 1990.0 # Base cloud infrastructure & RAG core fee
        
        # Tokens rate: ৳800 per 1M tokens
        token_cost = (tokens / 1_000_000.0) * 800.0
        
        # Extra seats beyond 2 included: ৳750/seat
        extra_seats = max(0, seats - 2)
        seat_cost = extra_seats * 750.0
        
        # Extra website widgets beyond 1 included: ৳1,200/widget
        extra_websites = max(0, websites - 1)
        website_cost = extra_websites * 1200.0
        
        # Extra knowledge docs beyond 50 included: ৳20/doc
        extra_docs = max(0, knowledge_docs - 50)
        docs_cost = extra_docs * 20.0
        
        # Add-on modules cost
        modules_cost = 0.0
        if modules:
            if modules.get("custom_branding", False):
                modules_cost += 1500.0
            if modules.get("sms_notifications", False):
                modules_cost += 1000.0
            if modules.get("dedicated_sla", False):
                modules_cost += 3500.0

        monthly_subtotal = base_platform_fee + token_cost + seat_cost + website_cost + docs_cost + modules_cost
        monthly_rounded = round(monthly_subtotal, -1) # Round to nearest 10
        
        # Annual: 15% discount
        annual_monthly_rate = round(monthly_rounded * 0.85, -1)
        annual_total = annual_monthly_rate * 12.0
        annual_savings = (monthly_rounded * 12.0) - annual_total

        return {
            "monthly_price_bdt": float(monthly_rounded),
            "annual_price_bdt": float(annual_monthly_rate),
            "effective_price_bdt": float(annual_monthly_rate if is_annual else monthly_rounded),
            "annual_savings_bdt": float(annual_savings),
            "tokens": tokens,
            "seats": seats,
            "websites": websites,
            "knowledge_docs": knowledge_docs,
            "breakdown": {
                "base_platform_bdt": base_platform_fee,
                "tokens_cost_bdt": round(token_cost, 2),
                "seats_cost_bdt": seat_cost,
                "websites_cost_bdt": website_cost,
                "docs_cost_bdt": docs_cost,
                "modules_cost_bdt": modules_cost
            }
        }
