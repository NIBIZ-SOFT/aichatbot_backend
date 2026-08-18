import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, delete
from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.models.all_models import (
    Tenant, User, UserRole, Subscription, SubscriptionTier, SubscriptionStatus,
    ApiKey, Webhook, UsageRecord, Notification, AuditLog,
    AIAssistant, KnowledgeBase, KnowledgeChunk, Website, Contact,
    Conversation, ConversationStatus, ConversationPriority, Message, SenderType
)

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

async def seed_database():
    print("=== Starting E-Commerce AIaaS SaaS Database Seeding (Bangladeshi Format + BDT Taka)... ===")
    
    async with AsyncSessionLocal() as db:
        # Create tables first & run column migrations
        from app.core.database import engine, Base
        from sqlalchemy import text
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS enabled_modules JSONB DEFAULT '{}'::jsonb;"))
            await conn.execute(text("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS csat_rating INTEGER;"))
            await conn.execute(text("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS csat_feedback VARCHAR(500);"))
            await conn.execute(text("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS first_response_time_ms INTEGER;"))
            await conn.execute(text("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP WITH TIME ZONE;"))

        # 1. Clean existing demo data if present (Idempotent seed)
        demo_slugs = [
            "padma-mart", "padma-digital-solutions", "acme-digital-solutions", 
            "daraz-seller-bd", "aarong-lifestyle", "chaldal-quick", "pickaboo-gadgets", "rokomari-books"
        ]
        for s in demo_slugs:
            existing_tenant_res = await db.execute(select(Tenant).where(Tenant.slug == s))
            existing_tenant = existing_tenant_res.scalars().first()
            if existing_tenant:
                print(f"[RESEED] Removing existing demo tenant '{s}' for clean deterministic reseeding...")
                await db.delete(existing_tenant)
                await db.commit()

        # Also clean super admin user if already exists for idempotent run
        await db.execute(delete(User).where(User.email.in_(["superadmin@enterprise.example", "superadmin@padmaai.example"])))
        await db.commit()

        # 2. Seed Primary Organization (Demo Tenant: Padma Mart Ltd. - Top BD E-Commerce Brand)
        tenant = Tenant(
            id=uuid.uuid4(),
            name="Padma Mart Ltd.",
            slug="padma-mart",
            custom_domain="shop.padmamart.com.bd",
            whitelabel_enabled=True,
            branding_config={
                "brand_name": "Padma Mart Live AI",
                "tagline": "Fastest Fashion, Gadgets & Lifestyle E-Commerce in Bangladesh",
                "primary_color": "#4F46E5",
                "company_address": "House 14, Road 7, Sector 3, Uttara, Dhaka-1230, Bangladesh",
                "support_phone": "+880 1837-586105",
                "currency": "BDT",
                "currency_symbol": "৳",
                "logo_url": "/logo.svg"
            },
            enabled_modules={
                "dashboard": True,
                "inbox": True,
                "contacts": True,
                "knowledge": True,
                "websites": True,
                "analytics": True,
                "usage": True,
                "team": True,
                "settings": True,
                "subscription": True
            }
        )
        db.add(tenant)
        await db.flush()

        # 3. Seed Subscription & Monthly Token Usage in BDT (৳)
        subscription = Subscription(
            tenant_id=tenant.id,
            tier=SubscriptionTier.ENTERPRISE,
            status=SubscriptionStatus.ACTIVE,
            monthly_token_limit=10_000_000, # 10M tokens
            monthly_conversation_limit=50_000,
            max_agents=25,
            max_websites=10,
            max_knowledge_docs=100,
            current_period_start=utc_now() - timedelta(days=15),
            current_period_end=utc_now() + timedelta(days=15)
        )
        db.add(subscription)

        # Historical monthly usage
        usage_current = UsageRecord(
            tenant_id=tenant.id,
            period_date=utc_now().strftime("%Y-%m"),
            prompt_tokens=1_842_763,
            completion_tokens=943_800,
            total_tokens=2_786_563,
            total_messages=18_420,
            total_conversations=1_850,
            estimated_cost_usd=42.50 # BDT ৳ equivalent
        )
        db.add(usage_current)

        # 4. Seed Users with Bangladeshi E-Commerce Staff Profiles
        seeded_users = {}
        
        # 4a. Platform Super Admin (Global - No Tenant Context)
        super_admin_user = User(
            tenant_id=None,
            email="superadmin@enterprise.example",
            hashed_password=get_password_hash("DemoPass123!"),
            full_name="Platform Super Admin",
            role=UserRole.SUPER_ADMIN,
            department="Platform Operations",
            is_active=True,
            is_online=False
        )
        db.add(super_admin_user)
        seeded_users["superadmin@enterprise.example"] = super_admin_user

        # 4b. Padma Mart Organization Owner & Specialized E-Commerce Staff
        padma_users_data = [
            ("owner@padmadigital.example", "Avijit Barua", UserRole.TENANT_OWNER, "Executive"),
            ("nusrat.support@padmadigital.example", "Nusrat Jahan", UserRole.SUPPORT_AGENT, "Customer Support & Orders"),
            ("ariful.sales@padmadigital.example", "Ariful Islam", UserRole.SALES_AGENT, "Sales & Styling Advisor"),
            ("mahmud.tech@padmadigital.example", "Mahmudul Hasan", UserRole.SUPPORT_AGENT, "Payment & Gateway Support"),
            ("sumaiya.analytics@padmadigital.example", "Sumaiya Akter", UserRole.VIEWER, "E-Commerce Business Analytics")
        ]

        for email, name, role, dept in padma_users_data:
            u = User(
                tenant_id=tenant.id,
                email=email,
                hashed_password=get_password_hash("DemoPass123!"),
                full_name=name,
                role=role,
                department=dept,
                is_active=True,
                is_online=True if role in [UserRole.SUPPORT_AGENT, UserRole.SALES_AGENT] else False
            )
            db.add(u)
            seeded_users[email] = u
        await db.flush()

        # 5. Seed Specialized E-Commerce AI Assistants
        assistant_support = AIAssistant(
            tenant_id=tenant.id,
            name="Padma Order & Support Bot",
            description="Tier 1 customer support: Order tracking, delivery coverage, bKash COD payments, and exchange requests.",
            personality_type="friendly",
            model_name="gemini-1.5-flash",
            temperature=0.25,
            top_p=0.95,
            max_output_tokens=1024,
            system_instruction="You are Padma Mart's friendly AI Customer Support Assistant. Greet customers warmly and answer questions about orders, deliveries, exchange policies, and payment methods using our knowledge base.",
            fallback_message="Let me connect you directly with Nusrat Jahan from our Order Support team.",
            auto_handover_keywords=["agent", "human", "talk to human", "order issue", "rider", "courier", "bKash dispute", "refund"]
        )
        assistant_sales = AIAssistant(
            tenant_id=tenant.id,
            name="Padma Fashion & Sales Advisor",
            description="Product recommendations, sizing guidance, Eid discounts, and coupon assistance.",
            personality_type="sales",
            model_name="gemini-1.5-pro",
            temperature=0.45,
            top_p=0.95,
            max_output_tokens=1024,
            system_instruction="You are Padma Mart's Fashion & Lifestyle Shopping Advisor. Help customers find matching clothes, suggest popular gadgets, and share active discount coupons like PADMA10 (10% off) and FREESHIP.",
            fallback_message="Connecting you with Ariful Islam from our Personal Styling & Sales team.",
            auto_handover_keywords=["custom size", "bulk order", "wholesale", "corporate gift", "discount code", "sales"]
        )
        assistant_tech = AIAssistant(
            tenant_id=tenant.id,
            name="Padma Payment & API Specialist",
            description="Assists with bKash/Nagad gateway verification, order webhook synchronization, and merchant APIs.",
            personality_type="technical",
            model_name="gemini-1.5-flash",
            temperature=0.1,
            top_p=0.9,
            max_output_tokens=2048,
            system_instruction="You are Padma Mart's Technical & Payment Integration Specialist. Assist customers and store partners with payment transaction IDs, webhook verification, and checkout errors.",
            fallback_message="Escalating this payment verification to Mahmudul Hasan.",
            auto_handover_keywords=["gateway error", "transaction failed", "double charge", "api", "webhook", "trxid"]
        )
        db.add_all([assistant_support, assistant_sales, assistant_tech])
        await db.flush()

        # 6. Seed E-Commerce Connected Storefronts & Widgets
        site_main = Website(
            tenant_id=tenant.id,
            name="Padma Mart Main Storefront",
            domain="padmamart.com.bd",
            widget_key=f"wg_shop_{uuid.uuid4().hex[:12]}",
            primary_color="#4F46E5",
            header_title="Padma Mart Live Support",
            welcome_message="Hello! Welcome to Padma Mart. Need help tracking an order, finding products, or checking sizes?",
            is_active=True
        )
        site_fashion = Website(
            tenant_id=tenant.id,
            name="Fashion & Lifestyle Hub",
            domain="fashion.padmamart.com.bd",
            widget_key=f"wg_fashion_{uuid.uuid4().hex[:12]}",
            primary_color="#EC4899",
            header_title="Padma Style Advisor AI",
            welcome_message="Welcome to Padma Fashion! Ask me about sizes, new Panjabi collections, or matching outfits.",
            is_active=True
        )
        site_gadgets = Website(
            tenant_id=tenant.id,
            name="Gadgets & Electronics Store",
            domain="gadgets.padmamart.com.bd",
            widget_key=f"wg_gadgets_{uuid.uuid4().hex[:12]}",
            primary_color="#06B6D4",
            header_title="Padma Gadget Assistant",
            welcome_message="Welcome to Padma Gadgets! Ask for earbuds, smartwatches, warranty terms, and discounts.",
            is_active=True
        )
        db.add_all([site_main, site_fashion, site_gadgets])
        await db.flush()

        # 7. Seed Rich E-Commerce RAG Knowledge Base in BDT (৳ Taka)
        # 7a. Product Catalog & Pricing Guide
        kb_catalog = KnowledgeBase(
            tenant_id=tenant.id,
            title="Padma Mart Product Catalog & Prices",
            description="Hot-selling fashion, electronics, lifestyle items, and pricing in BDT (৳).",
            category="Products & Pricing",
            source_type="document",
            chunk_count=3,
            status="indexed"
        )
        db.add(kb_catalog)
        await db.flush()

        chunks_catalog = [
            KnowledgeChunk(
                tenant_id=tenant.id,
                knowledge_base_id=kb_catalog.id,
                chunk_index=0,
                content="Men's Premium Cotton Panjabi Collection: Crafted from 100% Egyptian cotton. Available in Royal Blue, Black, Maroon, and White. Sizes: M (38), L (40), XL (42), XXL (44). Regular Price: ৳2,990 BDT. Eid Promotional Offer: ৳2,490 BDT.",
                metadata_json={"doc_title": kb_catalog.title, "category": "Fashion", "tokens": 48}
            ),
            KnowledgeChunk(
                tenant_id=tenant.id,
                knowledge_base_id=kb_catalog.id,
                chunk_index=1,
                content="Padma SoundPro Wireless ANC Earbuds: Active Noise Cancellation (35dB), 40-hour total battery life with fast charging case, Bluetooth 5.3, IPX5 water resistance. Price: ৳3,250 BDT with 6 months official warranty.",
                metadata_json={"doc_title": kb_catalog.title, "category": "Electronics", "tokens": 42}
            ),
            KnowledgeChunk(
                tenant_id=tenant.id,
                knowledge_base_id=kb_catalog.id,
                chunk_index=2,
                content="Padma Ultra Smartwatch Pro: 1.96-inch AMOLED display, Bluetooth calling, heart rate & SpO2 tracking, 100+ sports modes, 7-day battery life. Includes 2 silicone and leather straps. Price: ৳4,800 BDT.",
                metadata_json={"doc_title": kb_catalog.title, "category": "Electronics", "tokens": 40}
            )
        ]
        db.add_all(chunks_catalog)

        # 7b. Delivery, Shipping & Courier Coverage
        kb_delivery = KnowledgeBase(
            tenant_id=tenant.id,
            title="Delivery Coverage, Shipping Rates & Courier Guidelines",
            description="Shipping fees, delivery timelines, Steadfast/RedX tracking, and COD coverage across all 64 districts.",
            category="Shipping & Delivery",
            source_type="document",
            chunk_count=2,
            status="indexed"
        )
        db.add(kb_delivery)
        await db.flush()

        chunks_delivery = [
            KnowledgeChunk(
                tenant_id=tenant.id,
                knowledge_base_id=kb_delivery.id,
                chunk_index=0,
                content="Delivery inside Dhaka City (Mirpur, Gulshan, Banani, Dhanmondi, Uttara, Motijheel, Mohammadpur, Badda): Standard delivery charge is ৳60 BDT. Delivered within 24 hours. Express Same-Day delivery available for ৳120 BDT on orders placed before 1:00 PM.",
                metadata_json={"doc_title": kb_delivery.title, "category": "Shipping", "tokens": 45}
            ),
            KnowledgeChunk(
                tenant_id=tenant.id,
                knowledge_base_id=kb_delivery.id,
                chunk_index=1,
                content="Delivery Outside Dhaka (Chittagong, Sylhet, Rajshahi, Khulna, Barisal, Rangpur, and all 64 districts): Standard courier charge is ৳120 BDT via Steadfast Courier and RedX. Delivery timeline is 48 to 72 hours. FREE shipping on all orders over ৳3,000 BDT nationwide!",
                metadata_json={"doc_title": kb_delivery.title, "category": "Shipping", "tokens": 50}
            )
        ]
        db.add_all(chunks_delivery)

        # 7c. Return, Exchange & bKash Payment Policy
        kb_policy = KnowledgeBase(
            tenant_id=tenant.id,
            title="Return, Exchange & Payment Methods Policy",
            description="7-day size exchange, bKash/Nagad/Cards payment, Cash on Delivery (COD) rules, and refund timelines.",
            category="Policies & Terms",
            source_type="document",
            chunk_count=2,
            status="indexed"
        )
        db.add(kb_policy)
        await db.flush()

        chunks_policy = [
            KnowledgeChunk(
                tenant_id=tenant.id,
                knowledge_base_id=kb_policy.id,
                chunk_index=0,
                content="7-Day Easy Exchange Policy: If you have any size issues or received a defective product, you can request an exchange within 7 days of delivery. The item must be unused with original tags intact. We provide doorstep exchange in Dhaka or via courier return outside Dhaka.",
                metadata_json={"doc_title": kb_policy.title, "category": "Policies", "tokens": 46}
            ),
            KnowledgeChunk(
                tenant_id=tenant.id,
                knowledge_base_id=kb_policy.id,
                chunk_index=1,
                content="Payment Methods: We support Cash on Delivery (COD) across all 64 districts in Bangladesh. Digital payment options include bKash, Nagad, Rocket, Visa, Mastercard, and Amex. Prepayment via bKash receives an instant 1% cashback to your wallet. Active discount coupon: PADMA10 (10% off on orders above ৳1,500).",
                metadata_json={"doc_title": kb_policy.title, "category": "Payment", "tokens": 55}
            )
        ]
        db.add_all(chunks_policy)

        # 8. Seed E-Commerce Customers & Shoppers (Bangladeshi CRM Contacts)
        c_kamal = Contact(
            tenant_id=tenant.id,
            name="Kamal Hossain",
            email="kamal@dhakatrade.com.bd",
            phone="01711234567",
            company="Dhaka Trade International",
            tags=["VIP Gold Customer", "Frequent Buyer"],
            custom_attributes={
                "city": "Dhaka", 
                "area": "Mirpur-10", 
                "total_orders": 14, 
                "lifetime_spend_bdt": 38500,
                "preferred_payment": "Cash on Delivery"
            }
        )
        c_rokeya = Contact(
            tenant_id=tenant.id,
            name="Rokeya Sultana",
            email="rokeya.fashion@gmail.com",
            phone="01819987654",
            company="Bengal Fashion & Exports",
            tags=["Fashion Buyer", "High Intent"],
            custom_attributes={
                "city": "Dhaka", 
                "area": "Gulshan-2", 
                "total_orders": 8, 
                "lifetime_spend_bdt": 24900,
                "preferred_payment": "bKash Merchant"
            }
        )
        c_imran = Contact(
            tenant_id=tenant.id,
            name="Imran Chowdhury",
            email="imran.ctg@gmail.com",
            phone="01912334455",
            company="Chittagong Steel Traders",
            tags=["Gadget Lover", "Outside Dhaka"],
            custom_attributes={
                "city": "Chittagong", 
                "area": "Agrabad", 
                "total_orders": 5, 
                "lifetime_spend_bdt": 16800,
                "preferred_payment": "Cash on Delivery"
            }
        )
        c_sabrina = Contact(
            tenant_id=tenant.id,
            name="Sabrina Tasnim",
            email="sabrina.lifestyle@yahoo.com",
            phone="01610889900",
            company="Apex Enterprise BD",
            tags=["New Shopper", "Panjabi Order"],
            custom_attributes={
                "city": "Dhaka", 
                "area": "Uttara Sector-7", 
                "total_orders": 3, 
                "lifetime_spend_bdt": 8450,
                "preferred_payment": "bKash"
            }
        )
        c_rashed = Contact(
            tenant_id=tenant.id,
            name="Rashedul Haque",
            email="rashed.tech@gmail.com",
            phone="01515667788",
            company="TechBangla Labs",
            tags=["Gadgets Buyer", "Repeat Customer"],
            custom_attributes={
                "city": "Dhaka", 
                "area": "Dhanmondi-27", 
                "total_orders": 6, 
                "lifetime_spend_bdt": 19200,
                "preferred_payment": "Visa Card"
            }
        )

        db.add_all([c_kamal, c_rokeya, c_imran, c_sabrina, c_rashed])
        await db.flush()

        # 9. Seed Realistic E-Commerce Conversations with Live AI Handover Tickets
        nusrat_agent = seeded_users["nusrat.support@padmadigital.example"]
        ariful_agent = seeded_users["ariful.sales@padmadigital.example"]
        mahmud_agent = seeded_users["mahmud.tech@padmadigital.example"]

        # =========================================================================
        # CONVERSATION 1: Order Tracking & Steadfast Courier Status (Assigned to Nusrat)
        # =========================================================================
        conv_order_tracking = Conversation(
            tenant_id=tenant.id,
            website_id=site_main.id,
            contact_id=c_kamal.id,
            assigned_agent_id=nusrat_agent.id,
            visitor_session_id="vis_ord_kamal_8819",
            visitor_name="Kamal Hossain",
            visitor_email="kamal@dhakatrade.com.bd",
            status=ConversationStatus.RESOLVED,
            priority=ConversationPriority.URGENT,
            department="Customer Support",
            ai_paused=True,
            last_sentiment_score=-0.40,
            is_lead_detected=True,
            lead_data={"order_id": "ORD-88219", "phone": "01711234567"},
            csat_rating=5,
            csat_feedback="Nusrat Jahan called the Steadfast courier hub and my earbuds arrived before 6:30 PM. Great support!",
            first_response_time_ms=380,
            ai_summary="Customer inquiring about Order #ORD-88219 (SoundPro ANC Earbuds) delivery status in Mirpur-10. Resolved by Nusrat Jahan.",
            tags=["Urgent", "Order Tracking", "Steadfast Courier", "Mirpur Delivery"],
            unread_count=0,
            last_message_at=utc_now() - timedelta(minutes=3)
        )
        db.add(conv_order_tracking)
        await db.flush()

        msgs_1 = [
            Message(conversation_id=conv_order_tracking.id, sender_type=SenderType.VISITOR, content="Hi! I placed order #ORD-88219 for the SoundPro ANC Earbuds for delivery in Mirpur. What is the current status?", created_at=utc_now() - timedelta(minutes=15)),
            Message(conversation_id=conv_order_tracking.id, sender_type=SenderType.AI, content="Hello Kamal! Order #ORD-88219 was dispatched via Steadfast Courier with tracking number ST-99214. The package is out for delivery today in Mirpur-10. Total COD payable to the rider is ৳3,310 BDT (৳3,250 product + ৳60 standard delivery).", prompt_tokens=22, completion_tokens=48, latency_ms=420, created_at=utc_now() - timedelta(minutes=14)),
            Message(conversation_id=conv_order_tracking.id, sender_type=SenderType.VISITOR, content="The rider hasn't called yet and it is almost 5 PM. Can you please check with the courier hub urgently?", created_at=utc_now() - timedelta(minutes=8)),
            Message(conversation_id=conv_order_tracking.id, sender_type=SenderType.SYSTEM, content="⚠️ High priority courier inquiry. AI paused and routed to Nusrat Jahan (Customer Support & Orders).", created_at=utc_now() - timedelta(minutes=7)),
            Message(conversation_id=conv_order_tracking.id, sender_type=SenderType.AGENT, sender_name="Nusrat Jahan", is_internal_note=True, content="Whisper Note: Called Steadfast Mirpur hub manager (Rider: Al-Amin, 01720-998877). Package will be delivered by 6:30 PM.", created_at=utc_now() - timedelta(minutes=5)),
            Message(conversation_id=conv_order_tracking.id, sender_type=SenderType.AGENT, sender_name="Nusrat Jahan", content="Hello Kamal! I am Nusrat from Padma Mart Support. I just spoke with our Steadfast Mirpur delivery rider, Al-Amin. He is currently in Mirpur-1 and will reach your address by 6:30 PM today. Thank you for your patience!", created_at=utc_now() - timedelta(minutes=3))
        ]
        db.add_all(msgs_1)

        # =========================================================================
        # CONVERSATION 2: Panjabi Size Exchange & Coupon Codes (Assigned to Ariful)
        # =========================================================================
        conv_exchange = Conversation(
            tenant_id=tenant.id,
            website_id=site_fashion.id,
            contact_id=c_rokeya.id,
            assigned_agent_id=ariful_agent.id,
            visitor_session_id="vis_exchange_rokeya_550",
            visitor_name="Rokeya Sultana",
            visitor_email="rokeya.fashion@gmail.com",
            status=ConversationStatus.RESOLVED,
            priority=ConversationPriority.HIGH,
            department="Sales",
            ai_paused=True,
            last_sentiment_score=0.80,
            is_lead_detected=True,
            lead_data={"phone": "01819987654", "product": "Royal Blue Panjabi XL"},
            csat_rating=5,
            csat_feedback="Ariful helped me apply the PADMA10 coupon and booked doorstep size exchange for tomorrow. Super helpful!",
            first_response_time_ms=450,
            ai_summary="Size exchange request for Royal Blue Cotton Panjabi (Size L to XL) and inquiry for Eid coupon codes. Assigned to Ariful Islam.",
            tags=["Size Exchange", "Fashion Lead", "Eid Offer"],
            unread_count=0,
            last_message_at=utc_now() - timedelta(minutes=6)
        )
        db.add(conv_exchange)
        await db.flush()

        msgs_2 = [
            Message(conversation_id=conv_exchange.id, sender_type=SenderType.VISITOR, content="Hello! I received the Royal Blue Cotton Panjabi in Size L, but my brother needs Size XL (42). How can we exchange it?", created_at=utc_now() - timedelta(minutes=20)),
            Message(conversation_id=conv_exchange.id, sender_type=SenderType.AI, content="Hello Rokeya! We offer a 7-day easy doorstep exchange in Dhaka. As long as the product is unused with original tags, our rider will deliver the Size XL (42) to your address in Gulshan and collect the Size L at the same time! Would you like me to schedule this exchange for you?", prompt_tokens=25, completion_tokens=52, latency_ms=460, created_at=utc_now() - timedelta(minutes=19)),
            Message(conversation_id=conv_exchange.id, sender_type=SenderType.VISITOR, content="Yes please! Also, if I order another White Panjabi now, can I use the PADMA10 coupon code for 10% discount?", created_at=utc_now() - timedelta(minutes=12)),
            Message(conversation_id=conv_exchange.id, sender_type=SenderType.SYSTEM, content="🚨 Customer requested sales consultation & exchange scheduling. Assigned to Ariful Islam.", created_at=utc_now() - timedelta(minutes=10)),
            Message(conversation_id=conv_exchange.id, sender_type=SenderType.AGENT, sender_name="Ariful Islam", content="Hello Rokeya! I am Ariful from Padma Fashion. Yes, coupon code PADMA10 will give you an instant 10% discount (saving ৳249 BDT). I have booked your Size XL exchange for tomorrow afternoon and added the new White Panjabi with free express shipping!", created_at=utc_now() - timedelta(minutes=6))
        ]
        db.add_all(msgs_2)

        # =========================================================================
        # CONVERSATION 3: bKash Merchant Payment Verification (Assigned to Mahmud)
        # =========================================================================
        conv_payment = Conversation(
            tenant_id=tenant.id,
            website_id=site_gadgets.id,
            contact_id=c_imran.id,
            assigned_agent_id=mahmud_agent.id,
            visitor_session_id="vis_payment_imran_772",
            visitor_name="Imran Chowdhury",
            visitor_email="imran.ctg@gmail.com",
            status=ConversationStatus.RESOLVED,
            priority=ConversationPriority.MEDIUM,
            department="Technical Support",
            ai_paused=True,
            last_sentiment_score=0.35,
            is_lead_detected=False,
            csat_rating=5,
            csat_feedback="Mahmud verified my bKash merchant TrxID in 2 minutes and dispatched my order to Chittagong. Excellent service.",
            first_response_time_ms=310,
            ai_summary="bKash Merchant payment verification for Smartwatch Ultra (৳4,800 BDT, TrxID: 9X87KL22). Resolved by Mahmudul Hasan.",
            tags=["Payment Verified", "bKash TrxID", "Chittagong Order"],
            unread_count=0,
            last_message_at=utc_now() - timedelta(minutes=10)
        )
        db.add(conv_payment)
        await db.flush()

        msgs_3 = [
            Message(conversation_id=conv_payment.id, sender_type=SenderType.VISITOR, content="I ordered the Padma Ultra Smartwatch to Agrabad, Chittagong and paid ৳4,800 via bKash Merchant (TrxID: 9X87KL22). Could you verify if the payment was received?", created_at=utc_now() - timedelta(minutes=25)),
            Message(conversation_id=conv_payment.id, sender_type=SenderType.AGENT, sender_name="Mahmudul Hasan", content="Hello Imran! I am Mahmud from Payment Support. I have checked our bKash merchant statement—Transaction ID #9X87KL22 is confirmed and verified. Your smartwatch order is packed and will be dispatched to Chittagong via Steadfast Express with tracking number ST-77190.", created_at=utc_now() - timedelta(minutes=10))
        ]
        db.add_all(msgs_3)

        # 10. Seed Additional E-Commerce SaaS Tenants for Super Admin Platform View
        # Tenant 2: Daraz Seller Hub BD (Enterprise Tier)
        t_daraz = Tenant(
            id=uuid.uuid4(),
            name="Daraz Seller Hub BD",
            slug="daraz-seller-bd",
            custom_domain="support.darazseller.example",
            whitelabel_enabled=True,
            branding_config={"brand_name": "Daraz AI Support", "primary_color": "#F97316"},
            enabled_modules={
                "dashboard": True,
                "inbox": True,
                "contacts": False,
                "knowledge": True,
                "websites": False,
                "analytics": False,
                "usage": True,
                "team": False,
                "settings": True,
                "subscription": True
            }
        )
        db.add(t_daraz)
        await db.flush()

        sub_daraz = Subscription(
            tenant_id=t_daraz.id,
            tier=SubscriptionTier.ENTERPRISE,
            status=SubscriptionStatus.ACTIVE,
            monthly_token_limit=10_000_000,
            monthly_conversation_limit=50_000,
            max_agents=25,
            max_websites=10,
            current_period_start=utc_now() - timedelta(days=12),
            current_period_end=utc_now() + timedelta(days=18)
        )
        db.add(sub_daraz)

        u_daraz = User(
            tenant_id=t_daraz.id,
            email="owner@darazseller.example",
            hashed_password=get_password_hash("DemoPass123!"),
            full_name="Tareq Mahmud",
            role=UserRole.TENANT_OWNER,
            department="Executive",
            is_active=True
        )
        db.add(u_daraz)

        # Tenant 3: Aarong Lifestyle Retail (Growth Tier)
        t_aarong = Tenant(
            id=uuid.uuid4(),
            name="Aarong Lifestyle Retail",
            slug="aarong-lifestyle",
            custom_domain="help.aaronglifestyle.net",
            whitelabel_enabled=True,
            branding_config={"brand_name": "Aarong Live Assistant", "primary_color": "#B45309"}
        )
        db.add(t_aarong)
        await db.flush()

        sub_aarong = Subscription(
            tenant_id=t_aarong.id,
            tier=SubscriptionTier.GROWTH,
            status=SubscriptionStatus.ACTIVE,
            monthly_token_limit=2_500_000,
            monthly_conversation_limit=15_000,
            max_agents=10,
            max_websites=5,
            current_period_start=utc_now() - timedelta(days=8),
            current_period_end=utc_now() + timedelta(days=22)
        )
        db.add(sub_aarong)

        u_aarong = User(
            tenant_id=t_aarong.id,
            email="owner@aaronglifestyle.example",
            hashed_password=get_password_hash("DemoPass123!"),
            full_name="Farhana Islam",
            role=UserRole.TENANT_OWNER,
            department="Executive",
            is_active=True
        )
        db.add(u_aarong)

        # Tenant 4: Pickaboo Gadgets Hub (Growth Tier)
        t_pickaboo = Tenant(
            id=uuid.uuid4(),
            name="Pickaboo Gadgets Hub",
            slug="pickaboo-gadgets",
            custom_domain="support.pickaboohub.com.bd",
            whitelabel_enabled=False,
            branding_config={"brand_name": "Pickaboo Bot", "primary_color": "#0284C7"}
        )
        db.add(t_pickaboo)
        await db.flush()

        sub_pickaboo = Subscription(
            tenant_id=t_pickaboo.id,
            tier=SubscriptionTier.GROWTH,
            status=SubscriptionStatus.ACTIVE,
            monthly_token_limit=2_500_000,
            monthly_conversation_limit=15_000,
            max_agents=10,
            max_websites=5,
            current_period_start=utc_now() - timedelta(days=4),
            current_period_end=utc_now() + timedelta(days=26)
        )
        db.add(sub_pickaboo)

        u_pickaboo = User(
            tenant_id=t_pickaboo.id,
            email="owner@pickaboohub.example",
            hashed_password=get_password_hash("DemoPass123!"),
            full_name="Sajjad Hossain",
            role=UserRole.TENANT_OWNER,
            department="Executive",
            is_active=True
        )
        db.add(u_pickaboo)

        # Tenant 5: Rokomari Book Shop (Starter Tier)
        t_rokomari = Tenant(
            id=uuid.uuid4(),
            name="Rokomari Book Shop",
            slug="rokomari-books",
            custom_domain="help.rokomaribooks.com.bd",
            whitelabel_enabled=False,
            branding_config={"brand_name": "Rokomari Book Bot", "primary_color": "#059669"}
        )
        db.add(t_rokomari)
        await db.flush()

        sub_rokomari = Subscription(
            tenant_id=t_rokomari.id,
            tier=SubscriptionTier.STARTER,
            status=SubscriptionStatus.ACTIVE,
            monthly_token_limit=500_000,
            monthly_conversation_limit=5_000,
            max_agents=2,
            max_websites=1,
            current_period_start=utc_now() - timedelta(days=2),
            current_period_end=utc_now() + timedelta(days=28)
        )
        db.add(sub_rokomari)

        u_rokomari = User(
            tenant_id=t_rokomari.id,
            email="owner@rokomaribooks.example",
            hashed_password=get_password_hash("DemoPass123!"),
            full_name="Tanvir Ahmed",
            role=UserRole.TENANT_OWNER,
            department="Executive",
            is_active=True
        )
        db.add(u_rokomari)

        # Audit Logs
        log1 = AuditLog(
            tenant_id=None,
            action="TENANT_SUBSCRIPTION_ACTIVE",
            resource_type="Tenant",
            resource_id="Padma Mart Ltd.",
            metadata_json={"mrr_bdt": 49990, "tier": "Enterprise", "business_model": "E-Commerce"}
        )
        log2 = AuditLog(
            tenant_id=None,
            action="TENANT_SUBSCRIPTION_ACTIVE",
            resource_type="Tenant",
            resource_id="Daraz Seller Hub BD",
            metadata_json={"mrr_bdt": 49990, "tier": "Enterprise", "business_model": "Marketplace"}
        )
        db.add_all([log1, log2])

        await db.commit()
        print("[SUCCESS] E-Commerce Database Seeding Successfully Completed (Bangladeshi Format + BDT Taka)!")

if __name__ == "__main__":
    asyncio.run(seed_database())
