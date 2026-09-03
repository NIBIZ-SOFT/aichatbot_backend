import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, delete, text
from app.core.database import AsyncSessionLocal, engine, Base
from app.core.security import get_password_hash
from app.models.all_models import (
    Tenant, User, UserRole, Subscription, SubscriptionTier, SubscriptionStatus,
    ApiKey, Webhook, UsageRecord, Notification, AuditLog,
    AIAssistant, KnowledgeBase, KnowledgeChunk, Website, Contact,
    Conversation, ConversationStatus, ConversationPriority, Message, SenderType,
    Product, Order, PlatformSetting, PricingPlan, Coupon
)

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

async def seed_database(wipe_all_client_data: bool = True):
    """
    Official Production Database Seeder & Purge Tool for Jobab Chat Enterprise Platform.
    1. Runs dynamic column migrations without dropping tables.
    2. Purges all past test/trial client tenants, staff users, products, conversations, and orders.
    3. Initializes Master Super Admin user (admin@gmail.com / 12345678).
    4. Sets up Platform Settings (OpenRouter Universal Gateway, bKash PGW, EPS PGW).
    5. Seeds 4 SaaS Subscription Pricing Plans (Free, Starter, Growth, Enterprise).
    6. Seeds Official Promotional Coupons (WELCOME50, LAUNCH2026).
    """
    print(f"=== [PRODUCTION SEEDER] Initializing Jobab Chat Core Infrastructure (Purge All Test Clients: {wipe_all_client_data})... ===")
    
    async with AsyncSessionLocal() as db:
        # 1. Run dynamic column migrations (preserving table structure)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS business_category VARCHAR(50) DEFAULT 'ecommerce';"))
            await conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS enabled_modules JSONB DEFAULT '{}'::jsonb;"))
            await conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS ecommerce_settings JSONB DEFAULT '{}'::jsonb;"))
            await conn.execute(text("ALTER TABLE websites ADD COLUMN IF NOT EXISTS business_category VARCHAR(50) DEFAULT 'ecommerce';"))
            await conn.execute(text("ALTER TABLE websites ADD COLUMN IF NOT EXISTS ecommerce_config JSONB DEFAULT '{}'::jsonb;"))
            await conn.execute(text("ALTER TABLE websites ADD COLUMN IF NOT EXISTS branding_config JSONB DEFAULT '{}'::jsonb;"))
            await conn.execute(text("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS csat_rating INTEGER;"))
            await conn.execute(text("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS csat_feedback VARCHAR(500);"))
            await conn.execute(text("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS first_response_time_ms INTEGER;"))
            await conn.execute(text("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP WITH TIME ZONE;"))
            await conn.execute(text("ALTER TABLE pricing_plans ADD COLUMN IF NOT EXISTS is_pay_as_you_go BOOLEAN DEFAULT FALSE;"))
            await conn.execute(text("ALTER TABLE pricing_plans ADD COLUMN IF NOT EXISTS per_1k_tokens_rate_bdt FLOAT DEFAULT 0.15;"))
            await conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS locked_price_bdt FLOAT DEFAULT 0.0;"))
            await conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS locked_token_limit INTEGER DEFAULT 500000;"))
            await conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS is_custom_deal BOOLEAN DEFAULT FALSE;"))
            await conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS deal_notes VARCHAR(500);"))
            await conn.execute(text("ALTER TABLE tenant_wallets ADD COLUMN IF NOT EXISTS is_custom_rate BOOLEAN DEFAULT FALSE;"))
            await conn.execute(text("ALTER TABLE tenant_wallets ADD COLUMN IF NOT EXISTS contract_locked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();"))
            await conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS metadata_json JSONB DEFAULT '{}'::jsonb;"))

        # 2. Complete Atomic Purge of all previous test/trial client tenants and accounts
        if wipe_all_client_data:
            print("[RESET] Purging all previous trial client tenants, accounts, and demo data from PostgreSQL...")
            async with engine.begin() as conn:
                try:
                    tables_to_truncate = [
                        "messages", "conversations", "orders", "products",
                        "knowledge_chunks", "knowledge_bases", "ai_assistants",
                        "websites", "contacts", "usage_records", "audit_logs",
                        "notifications", "wallet_transactions", "tenant_wallets",
                        "coupon_redemptions", "api_keys", "webhooks", "subscriptions",
                        "users", "tenants"
                    ]
                    await conn.execute(text(f"TRUNCATE TABLE {', '.join(tables_to_truncate)} CASCADE;"))
                    print("[RESET] All test client accounts, tenants, and sessions successfully truncated!")
                except Exception as e:
                    print(f"[RESET WARNING] Truncate fallback: {e}")
                    # Fallback individual deletes
                    for tbl in ["messages", "conversations", "orders", "products", "knowledge_chunks", "knowledge_bases", "ai_assistants", "websites", "contacts", "usage_records", "audit_logs", "notifications", "wallet_transactions", "tenant_wallets", "coupon_redemptions", "api_keys", "webhooks", "subscriptions", "users", "tenants"]:
                        try:
                            await conn.execute(text(f"DELETE FROM {tbl};"))
                        except Exception:
                            pass

        # 3. Seed Master Super Admin Account
        admin_res = await db.execute(select(User).where(User.email == "admin@gmail.com"))
        admin_user = admin_res.scalars().first()
        if not admin_user:
            print("[SEED] Creating Master Super Admin: admin@gmail.com...")
            admin_user = User(
                id=uuid.uuid4(),
                email="admin@gmail.com",
                hashed_password=get_password_hash("12345678"),
                full_name="Platform Super Administrator",
                role=UserRole.SUPER_ADMIN,
                tenant_id=None,
                is_active=True,
                created_at=utc_now()
            )
            db.add(admin_user)
            await db.commit()
        else:
            print("[SEED] Master Super Admin already exists.")

        # 4. Seed Platform Settings (AI Universal Gateway & Payment Gateways)
        # 4a. Platform AI Gateway Config
        ai_setting_res = await db.execute(select(PlatformSetting).where(PlatformSetting.key == "platform_ai_config"))
        ai_setting = ai_setting_res.scalars().first()
        if not ai_setting:
            print("[SEED] Seeding Platform AI Gateway Settings...")
            ai_setting = PlatformSetting(
                id=uuid.uuid4(),
                key="platform_ai_config",
                category="ai",
                description="Global OpenRouter AI Gateway Credentials and Default LLM Models",
                is_secret=True,
                value_json={
                    "gateway_api_key": "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",
                    "base_url": "https://openrouter.ai/api/v1",
                    "master_model": "google/gemini-2.5-flash",
                    "fallback_model": "google/gemini-2.5-flash-lite",
                    "embedding_model": "text-embedding-004",
                    "temperature": 0.3,
                    "max_output_tokens": 2048,
                    "system_instruction_baseline": "You are an enterprise AI customer communication assistant for Jobab Chat Platform."
                },
                created_at=utc_now(),
                updated_at=utc_now()
            )
            db.add(ai_setting)

        # 4b. Platform bKash PGW Config
        bkash_setting_res = await db.execute(select(PlatformSetting).where(PlatformSetting.key == "platform_bkash_config"))
        bkash_setting = bkash_setting_res.scalars().first()
        if not bkash_setting:
            print("[SEED] Seeding Platform bKash Gateway Settings...")
            bkash_setting = PlatformSetting(
                id=uuid.uuid4(),
                key="platform_bkash_config",
                category="payment",
                description="Platform SaaS Subscription bKash Tokenized Checkout Merchant Credentials",
                is_secret=True,
                value_json={
                    "is_sandbox": True,
                    "app_key": "sandbox_app_key_placeholder",
                    "app_secret": "sandbox_app_secret_placeholder",
                    "username": "sandbox_user",
                    "password": "sandbox_password",
                    "merchant_msisdn": "01770618575"
                },
                created_at=utc_now(),
                updated_at=utc_now()
            )
            db.add(bkash_setting)

        # 4c. Platform EPS PGW Config
        eps_setting_res = await db.execute(select(PlatformSetting).where(PlatformSetting.key == "platform_eps_config"))
        eps_setting = eps_setting_res.scalars().first()
        if not eps_setting:
            print("[SEED] Seeding Platform EPS Gateway Settings...")
            eps_setting = PlatformSetting(
                id=uuid.uuid4(),
                key="platform_eps_config",
                category="payment",
                description="Platform SaaS Subscription EPS Multi-Channel Payment Gateway Merchant Credentials",
                is_secret=True,
                value_json={
                    "is_sandbox": True,
                    "merchant_id": "sandbox_merchant_id",
                    "store_id": "sandbox_store_id",
                    "secret_key": "sandbox_secret_key"
                },
                created_at=utc_now(),
                updated_at=utc_now()
            )
            db.add(eps_setting)

        await db.commit()

        # 5. Seed Official SaaS Subscription Pricing Plans
        plans_data = [
            {
                "name": "Free Plan",
                "code": "free",
                "description": "Essential AI Chatbot widget for testing and early validation.",
                "monthly_price_bdt": 0.0,
                "annual_price_bdt": 0.0,
                "monthly_token_limit": 50000,
                "monthly_conversation_limit": 50,
                "max_agents": 1,
                "max_websites": 1,
                "max_knowledge_docs": 2,
                "features": [
                    "50,000 AI Tokens / month",
                    "1 Active Website Widget",
                    "1 Staff / Agent Seat",
                    "2 Knowledge Base Documents",
                    "Standard AI Response Speed",
                    "Community Support"
                ],
                "badge_text": "Free Forever",
                "is_featured": False,
                "is_active": True,
                "sort_order": 1
            },
            {
                "name": "Starter Plan",
                "code": "starter",
                "description": "Ideal for growing online stores, direct retail, and active customer support desks.",
                "monthly_price_bdt": 4990.0,
                "annual_price_bdt": 4240.0,
                "monthly_token_limit": 500000,
                "monthly_conversation_limit": 200,
                "max_agents": 2,
                "max_websites": 2,
                "max_knowledge_docs": 10,
                "features": [
                    "500,000 AI Tokens / month",
                    "2 Active Website Widgets",
                    "2 Staff / Agent Seats",
                    "10 Knowledge Base Documents",
                    "bKash & EPS Automated Billing",
                    "Basic CSAT & Analytics",
                    "Email Support (24h SLA)"
                ],
                "badge_text": "Starter",
                "is_featured": False,
                "is_active": True,
                "sort_order": 2
            },
            {
                "name": "Growth Plan",
                "code": "growth",
                "description": "High-volume autonomous AI resolutions, multi-channel widgets, and automated commerce.",
                "monthly_price_bdt": 19990.0,
                "annual_price_bdt": 16990.0,
                "monthly_token_limit": 2500000,
                "monthly_conversation_limit": 1000,
                "max_agents": 5,
                "max_websites": 5,
                "max_knowledge_docs": 50,
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
                "badge_text": "Most Popular",
                "is_featured": True,
                "is_active": True,
                "sort_order": 3
            },
            {
                "name": "Enterprise Plan",
                "code": "enterprise",
                "description": "Large corporations, ERP integrations, customized LLM guardrails, and dedicated SLAs.",
                "monthly_price_bdt": 49990.0,
                "annual_price_bdt": 42490.0,
                "monthly_token_limit": 10000000,
                "monthly_conversation_limit": 5000,
                "max_agents": 20,
                "max_websites": 20,
                "max_knowledge_docs": 200,
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
                "badge_text": "Enterprise",
                "is_featured": False,
                "is_active": True,
                "sort_order": 4
            }
        ]

        for p_data in plans_data:
            plan_res = await db.execute(select(PricingPlan).where(PricingPlan.code == p_data["code"]))
            existing_plan = plan_res.scalars().first()
            if not existing_plan:
                print(f"[SEED] Creating SaaS Plan: {p_data['name']} (৳{p_data['monthly_price_bdt']} BDT)...")
                new_plan = PricingPlan(
                    id=uuid.uuid4(),
                    name=p_data["name"],
                    code=p_data["code"],
                    description=p_data["description"],
                    monthly_price_bdt=p_data["monthly_price_bdt"],
                    annual_price_bdt=p_data["annual_price_bdt"],
                    monthly_token_limit=p_data["monthly_token_limit"],
                    monthly_conversation_limit=p_data["monthly_conversation_limit"],
                    max_agents=p_data["max_agents"],
                    max_websites=p_data["max_websites"],
                    max_knowledge_docs=p_data["max_knowledge_docs"],
                    features=p_data["features"],
                    badge_text=p_data["badge_text"],
                    is_featured=p_data["is_featured"],
                    is_active=p_data["is_active"],
                    sort_order=p_data["sort_order"],
                    created_at=utc_now(),
                    updated_at=utc_now()
                )
                db.add(new_plan)
            else:
                # Update existing plan with clean official parameters
                existing_plan.name = p_data["name"]
                existing_plan.monthly_price_bdt = p_data["monthly_price_bdt"]
                existing_plan.annual_price_bdt = p_data["annual_price_bdt"]
                existing_plan.monthly_token_limit = p_data["monthly_token_limit"]
                existing_plan.monthly_conversation_limit = p_data["monthly_conversation_limit"]
                existing_plan.max_agents = p_data["max_agents"]
                existing_plan.max_websites = p_data["max_websites"]
                existing_plan.max_knowledge_docs = p_data["max_knowledge_docs"]
                existing_plan.features = p_data["features"]
                existing_plan.badge_text = p_data["badge_text"]
                existing_plan.is_featured = p_data["is_featured"]
                existing_plan.sort_order = p_data["sort_order"]

        await db.commit()

        # 6. Seed Official Promotional Coupons
        coupons_data = [
            {
                "code": "WELCOME50",
                "description": "50% Discount on First Month Subscription",
                "discount_type": "percentage",
                "discount_value": 50.0,
                "max_discount_amount_bdt": 5000.0,
                "min_purchase_amount_bdt": 1000.0,
                "max_redemptions": 500,
                "is_active": True,
                "valid_until": utc_now() + timedelta(days=365)
            },
            {
                "code": "LAUNCH2026",
                "description": "20% Discount for Early Platform Adopters",
                "discount_type": "percentage",
                "discount_value": 20.0,
                "max_discount_amount_bdt": 10000.0,
                "min_purchase_amount_bdt": 0.0,
                "max_redemptions": 1000,
                "is_active": True,
                "valid_until": utc_now() + timedelta(days=365)
            }
        ]

        for c_data in coupons_data:
            c_res = await db.execute(select(Coupon).where(Coupon.code == c_data["code"]))
            existing_c = c_res.scalars().first()
            if not existing_c:
                print(f"[SEED] Creating Official Promo Coupon: {c_data['code']} ({c_data['discount_value']}% OFF)...")
                new_c = Coupon(
                    id=uuid.uuid4(),
                    code=c_data["code"],
                    description=c_data["description"],
                    discount_type=c_data["discount_type"],
                    discount_value=c_data["discount_value"],
                    max_discount_amount_bdt=c_data["max_discount_amount_bdt"],
                    min_purchase_amount_bdt=c_data["min_purchase_amount_bdt"],
                    max_redemptions=c_data["max_redemptions"],
                    is_active=c_data["is_active"],
                    valid_from=utc_now(),
                    valid_until=c_data["valid_until"],
                    created_at=utc_now()
                )
                db.add(new_c)

        # 7. Seed Official Platform Live Support Website (wgt_platform_live_support)
        support_stmt = select(Website).where(Website.widget_key == "wgt_platform_live_support")
        existing_support = (await db.execute(support_stmt)).scalars().first()
        if not existing_support:
            print("[SEED] Creating Official Platform Live Support Chatbot (wgt_platform_live_support)...")
            support_tenant_stmt = select(Tenant).where(Tenant.slug == "platform-support")
            support_tenant = (await db.execute(support_tenant_stmt)).scalars().first()
            if not support_tenant:
                support_tenant = Tenant(
                    id=uuid.uuid4(),
                    name="Jobab Chat Platform Support",
                    slug="platform-support",
                    subscription_tier=SubscriptionTier.ENTERPRISE,
                    is_active=True,
                    monthly_token_limit=100000000,
                    used_tokens=0,
                    business_category="saas"
                )
                db.add(support_tenant)
                await db.flush()

            asst_stmt = select(AIAssistant).where(AIAssistant.tenant_id == support_tenant.id)
            assistant = (await db.execute(asst_stmt)).scalars().first()
            if not assistant:
                assistant = AIAssistant(
                    id=uuid.uuid4(),
                    tenant_id=support_tenant.id,
                    name="Jobab Live Concierge",
                    system_prompt="You are the official Jobab Chat live sales & customer support specialist. Help visitors with information about pricing plans, bKash/Nagad integration, AI features, and lead booking in both English and Bengali.",
                    model_name="google/gemini-2.5-flash",
                    temperature=0.3
                )
                db.add(assistant)
                await db.flush()

            new_website = Website(
                id=uuid.uuid4(),
                tenant_id=support_tenant.id,
                assistant_id=assistant.id,
                name="Platform Official Live Support Chatbot",
                domain="jobab.chat",
                widget_key="wgt_platform_live_support",
                is_active=True,
                business_category="saas",
                branding_config={
                    "primary_color": "#4F46E5",
                    "header_title": "Jobab Chat Support",
                    "welcome_message": "Hello! Welcome to Jobab Chat. How can we help your business today?"
                }
            )
            db.add(new_website)
            await db.commit()
            print("[SEED] Official Platform Live Support Chatbot seeded successfully!")
        else:
            if not existing_support.is_active:
                existing_support.is_active = True
                await db.commit()
            print("[SEED] Official Platform Live Support Chatbot already active.")

        await db.commit()

    print("=== [PRODUCTION SEEDER COMPLETE] Database is 100% clean and production-ready! ===")
    print("Master Super Admin: admin@gmail.com / 12345678")

if __name__ == "__main__":
    asyncio.run(seed_database())
