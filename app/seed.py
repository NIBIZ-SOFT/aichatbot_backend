import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    Conversation, ConversationStatus, ConversationPriority, Message, SenderType,
    Product, Order
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
            await conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS metadata_json JSONB DEFAULT '{}'::jsonb;"))

        # 1. Clean existing demo data if present (Idempotent seed)
        demo_slugs = [
            "padma-mart", "apex-erp-cloud", "horizon-retail", "padma-digital-solutions", "acme-digital-solutions", 
            "daraz-seller-bd", "aarong-lifestyle", "chaldal-quick", "pickaboo-gadgets", "rokomari-books"
        ]
        for s in demo_slugs:
            existing_tenant_res = await db.execute(select(Tenant).where(Tenant.slug == s))
            existing_tenant = existing_tenant_res.scalars().first()
            if existing_tenant:
                print(f"[RESEED] Removing existing demo tenant '{s}' for clean deterministic reseeding...")
                await db.delete(existing_tenant)
                await db.commit()

        # Also clean super admin user and demo client users if already exists for idempotent run
        await db.execute(delete(User).where(User.email.in_([
            "admin@gmail.com", "ecommerceclient1@gmail.com", "erpclient1@gmail.com", "ecommerceclient2@gmail.com",
            "client@gmail.com", "client2@gmail.com",
            "superadmin@enterprise.example", "superadmin@padmaai.example", 
            "owner@padmadigital.example", "owner@padmaai.example"
        ])))
        await db.commit()

        # 2. Seed Primary Organization (Demo Tenant: Padma Mart Ltd. - Top BD E-Commerce Brand)
        tenant = Tenant(
            id=uuid.uuid4(),
            name="Padma Mart Ltd.",
            slug="padma-mart",
            business_category="ecommerce",
            custom_domain="shop.padmamart.com.bd",
            whitelabel_enabled=True,
            branding_config={
                "brand_name": "Padma Mart Live AI",
                "tagline": "Fastest Fashion, Gadgets & Lifestyle E-Commerce in Bangladesh",
                "primary_color": "#4F46E5",
                "company_address": "House 14, Road 7, Sector 3, Uttara, Dhaka-1230, Bangladesh",
                "support_hotline": "+880 1700-112233",
                "vat_registration_no": "BIN-002948192-0102"
            },
            enabled_modules={
                "dashboard": True,
                "inbox": True,
                "contacts": True,
                "products": True,
                "orders": True,
                "knowledge": True,
                "websites": True,
                "analytics": True,
                "usage": True,
                "team": True,
                "settings": True,
                "subscription": True
            },
            ecommerce_settings={
                "cod_enabled": True,
                "delivery_charge_inside_dhaka": 60.0,
                "delivery_charge_outside_dhaka": 120.0,
                "bkash": {
                    "enabled": True,
                    "is_sandbox": True,
                    "base_url": "https://tokenized.sandbox.bka.sh/v1.2.0-beta",
                    "app_key": "4f6o0cjiki2rfm34kfdadl1eqq",
                    "username": "sandboxTokenizedUser02"
                },
                "sms": {
                    "enabled": True,
                    "provider": "smsmatrix",
                    "sender_id": "PadmaMart"
                },
                "sms_order_template": "Dear {{customer_name}}, your order #{{order_id}} for ৳{{total_amount}} is placed at Padma Mart! Thank you for shopping with us."
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
            email="admin@gmail.com",
            hashed_password=get_password_hash("12345678"),
            full_name="Platform Super Admin",
            role=UserRole.SUPER_ADMIN,
            department="Platform Operations",
            is_active=True,
            is_online=False
        )
        db.add(super_admin_user)
        seeded_users["admin@gmail.com"] = super_admin_user

        # 4b. Padma Mart Organization Owner (E-Commerce Client 1) & Specialized Staff
        padma_users_data = [
            ("ecommerceclient1@gmail.com", "E-Commerce Client 1 (Padma Mart)", UserRole.TENANT_OWNER, "Executive"),
            ("nusrat.support@padmadigital.example", "Nusrat Jahan", UserRole.SUPPORT_AGENT, "Customer Support & Orders"),
            ("ariful.sales@padmadigital.example", "Ariful Islam", UserRole.SALES_AGENT, "Sales & Styling Advisor"),
            ("mahmud.tech@padmadigital.example", "Mahmudul Hasan", UserRole.SUPPORT_AGENT, "Payment & Gateway Support"),
            ("sumaiya.analytics@padmadigital.example", "Sumaiya Akter", UserRole.VIEWER, "E-Commerce Business Analytics")
        ]

        for email, name, role, dept in padma_users_data:
            u = User(
                tenant_id=tenant.id,
                email=email,
                hashed_password=get_password_hash("12345678"),
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
            system_instruction="""You are Padma Mart's intelligent E-Commerce Assistant.
Padma Mart offers premium fashion, smartwatches, earbuds, and lifestyle products with nationwide delivery in Bangladesh (Inside Dhaka ৳60 BDT, Outside Dhaka ৳120 BDT | COD & bKash).

STRICT CONCISENESS & TOKEN EFFICIENCY RULES:
1. ALWAYS keep responses extremely brief, crisp, and direct (1 to 2 short sentences max). NEVER write long essays, repetitive tables, multi-product historical calculations, or lengthy delivery essays.
2. When a customer mentions, selects, or wants to buy a product (e.g. "Padma Ultra Smartwatch Pro 2 ta dao"):
   - Simply confirm the selected product and quantity in 1 short sentence.
   - Instruct them to tap "⚡ Buy Now" on the product card below to complete the 1-click order (or "🛒 Add to Cart" to add to bag).
   - Example response: "Padma Ultra Smartwatch Pro (২টি) সিলেক্ট করা হয়েছে। নিচের কার্ডের **⚡ Buy Now** বাটনে ক্লিক করে সরাসরি অর্ডার সম্পন্ন করতে পারেন।"
3. Do NOT repeat delivery charges, full breakdowns, or ask for address in text unless explicitly requested by the customer, because the interactive card handles the purchase workflow directly.
4. Speak in friendly, natural Bengali (or English if the customer writes in English).""",
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
            assistant_id=assistant_support.id,
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
            assistant_id=assistant_sales.id,
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
            assistant_id=assistant_tech.id,
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

        # 6b. Seed Products into Products Module (Padma Mart - client@gmail.com)
        prod_panjabi = Product(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            title="Men's Premium Cotton Panjabi Collection",
            slug="mens-premium-cotton-panjabi-collection",
            category="Fashion",
            sku="SKU-PANJABI-01",
            unit_price=2990.0,
            selling_price=2490.0,
            stock_quantity=85,
            stock_status="in_stock",
            images=["https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?w=600&auto=format&fit=crop&q=80"],
            description="100% Egyptian Cotton handcrafted Panjabi with intricate thread embroidery on collar and placket. Available in Royal Blue, Black, Maroon, and White.",
            specifications={"Material": "100% Egyptian Cotton", "Sizes": "M (38), L (40), XL (42), XXL (44)", "Fit": "Slim Fit & Regular Fit", "Occasion": "Eid / Festive"},
            tags=["eid", "festive", "cotton", "men", "panjabi"],
            priority=10
        )
        prod_earbuds = Product(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            title="Padma SoundPro Wireless ANC Earbuds",
            slug="padma-soundpro-wireless-anc-earbuds",
            category="Electronics",
            sku="SKU-AUDIO-02",
            unit_price=3990.0,
            selling_price=3250.0,
            stock_quantity=42,
            stock_status="in_stock",
            images=["https://images.unsplash.com/photo-1590658268037-6bf12165a8df?w=600&auto=format&fit=crop&q=80"],
            description="High-fidelity audio with 35dB Active Noise Cancellation, Bluetooth 5.3, 40-hour total battery life with wireless charging case.",
            specifications={"Battery Life": "8h earbuds + 32h case", "ANC": "35dB Active Noise Cancellation", "Water Resistance": "IPX5", "Warranty": "6 Months Official"},
            tags=["earbuds", "anc", "wireless", "audio", "bluetooth"],
            priority=9
        )
        prod_smartwatch = Product(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            title="Padma Ultra Smartwatch Pro",
            slug="padma-ultra-smartwatch-pro",
            category="Electronics",
            sku="SKU-WATCH-03",
            unit_price=5500.0,
            selling_price=4800.0,
            stock_quantity=30,
            stock_status="in_stock",
            images=["https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=600&auto=format&fit=crop&q=80"],
            description="1.96-inch AMOLED always-on display, Bluetooth calling with noise reduction mic, 24/7 Heart rate & SpO2 monitoring, and 100+ sports modes.",
            specifications={"Display": "1.96-inch AMOLED (410x502)", "Battery": "7-day battery life", "Straps": "Includes 2 straps (Silicone & Leather)", "Waterproof": "IP68"},
            tags=["smartwatch", "amoled", "calling", "fitness", "watch"],
            priority=8
        )
        prod_saree = Product(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            title="Handloom Pure Dhakai Jamdani Saree",
            slug="handloom-pure-dhakai-jamdani-saree",
            category="Fashion",
            sku="SKU-SAREE-04",
            unit_price=8200.0,
            selling_price=6500.0,
            stock_quantity=20,
            stock_status="in_stock",
            images=["https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=600&auto=format&fit=crop&q=80"],
            description="Traditional 84-count cotton silk hand-woven Dhakai Jamdani saree with fine golden zari floral motifs, perfect for weddings and cultural festivals.",
            specifications={"Fabric": "Pure Cotton Silk", "Length": "12 Haat with Blouse Piece", "Craft": "Handloom Weave", "Color": "Crimson Red with Golden Zari"},
            tags=["saree", "jamdani", "dhakai", "women", "traditional", "wedding"],
            priority=7
        )
        prod_polo = Product(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            title="Men's Classic Slim-Fit Polo T-Shirt",
            slug="mens-classic-slim-fit-polo-t-shirt",
            category="Fashion",
            sku="SKU-POLO-05",
            unit_price=1450.0,
            selling_price=1150.0,
            stock_quantity=110,
            stock_status="in_stock",
            images=["https://images.unsplash.com/photo-1581655353564-df123a1eb820?w=600&auto=format&fit=crop&q=80"],
            description="220 GSM breathable pique cotton polo shirt with ribbed collar, horn buttons, and anti-shrink enzyme wash finish.",
            specifications={"Fabric": "100% Pique Cotton (220 GSM)", "Sizes": "S, M, L, XL, XXL", "Colors": "Navy Blue, Olive Green, Charcoal, White"},
            tags=["polo", "t-shirt", "casual", "men", "summer"],
            priority=6
        )
        prod_kurti = Product(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            title="Embroidered Georgette Designer Kurti",
            slug="embroidered-georgette-designer-kurti",
            category="Fashion",
            sku="SKU-KURTI-06",
            unit_price=3500.0,
            selling_price=2850.0,
            stock_quantity=45,
            stock_status="in_stock",
            images=["https://images.unsplash.com/photo-1583391733975-0245a4943f21?w=600&auto=format&fit=crop&q=80"],
            description="Contemporary flared A-line georgette kurti with intricate Kashmiri neckline thread embroidery and inner santoon lining.",
            specifications={"Fabric": "Pure Georgette with Lining", "Sizes": "38 (M), 40 (L), 42 (XL), 44 (XXL)", "Work": "Kashmiri Thread Embroidery"},
            tags=["kurti", "women", "georgette", "designer", "ethnic"],
            priority=5
        )
        prod_soundbar = Product(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            title="Padma BassBoom 120W Bluetooth Soundbar",
            slug="padma-bassboom-120w-bluetooth-soundbar",
            category="Electronics",
            sku="SKU-AUDIO-07",
            unit_price=9990.0,
            selling_price=7990.0,
            stock_quantity=18,
            stock_status="in_stock",
            images=["https://images.unsplash.com/photo-1545454675-3531b543be5d?w=600&auto=format&fit=crop&q=80"],
            description="120W cinematic home theater soundbar with wireless subwoofer, HDMI eARC, Optical, AUX, and Bluetooth 5.3 3D surround sound.",
            specifications={"Output Power": "120W RMS (60W Bar + 60W Subwoofer)", "Inputs": "HDMI eARC, Optical, AUX, Bluetooth, USB", "Modes": "Movie, Music, News, 3D Surround"},
            tags=["soundbar", "speaker", "home theater", "bass", "audio"],
            priority=4
        )
        prod_powerbank = Product(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            title="Padma TurboCharge 20000mAh 65W Power Bank",
            slug="padma-turbocharge-20000mah-65w-power-bank",
            category="Electronics",
            sku="SKU-PWR-08",
            unit_price=2800.0,
            selling_price=2200.0,
            stock_quantity=50,
            stock_status="in_stock",
            images=["https://images.unsplash.com/photo-1609592424300-349f285f502d?w=600&auto=format&fit=crop&q=80"],
            description="Ultra-fast 65W Power Delivery laptop and phone power bank with digital LED battery percentage display and aircraft safety approval.",
            specifications={"Capacity": "20,000mAh (74Wh)", "Max Output": "65W PD / PPS / QC 3.0", "Ports": "2x USB-C + 1x USB-A", "Weight": "380g"},
            tags=["power bank", "charger", "fast charging", "battery", "laptop"],
            priority=4
        )
        prod_oxford = Product(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            title="Handcrafted Genuine Leather Oxford Shoes",
            slug="handcrafted-genuine-leather-oxford-shoes",
            category="Footwear",
            sku="SKU-SHOE-09",
            unit_price=5200.0,
            selling_price=4200.0,
            stock_quantity=35,
            stock_status="in_stock",
            images=["https://images.unsplash.com/photo-1614252235316-8c857d38b5f4?w=600&auto=format&fit=crop&q=80"],
            description="Full-grain imported cow leather Oxford formal dress shoes with padded orthopedic memory foam insole and anti-slip rubber outsole.",
            specifications={"Upper Material": "100% Genuine Full-Grain Cow Leather", "Sole": "Durable Anti-Slip Rubber", "Sizes": "40, 41, 42, 43, 44", "Color": "Burnished Tan / Jet Black"},
            tags=["shoes", "oxford", "leather", "formal", "men", "footwear"],
            priority=3
        )
        prod_sneakers = Product(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            title="Padma AirFlex Breathable Running Sneakers",
            slug="padma-airflex-breathable-running-sneakers",
            category="Footwear",
            sku="SKU-SHOE-10",
            unit_price=3200.0,
            selling_price=2650.0,
            stock_quantity=60,
            stock_status="in_stock",
            images=["https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=600&auto=format&fit=crop&q=80"],
            description="Ultra-lightweight mesh knit running sneakers with responsive air-cushioned midsole for gym, sports, and daily walking comfort.",
            specifications={"Upper": "Flyknit Breathable Mesh", "Midsole": "High-Rebound EVA Air Cushion", "Sizes": "39, 40, 41, 42, 43, 44", "Weight": "240g per shoe"},
            tags=["sneakers", "running", "sports", "shoes", "gym", "footwear"],
            priority=3
        )
        prod_backpack = Product(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            title="Waterproof Anti-Theft 15.6\" Laptop Backpack",
            slug="waterproof-anti-theft-15-6-laptop-backpack",
            category="Bags",
            sku="SKU-BAG-11",
            unit_price=2400.0,
            selling_price=1850.0,
            stock_quantity=75,
            stock_status="in_stock",
            images=["https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=600&auto=format&fit=crop&q=80"],
            description="High-density water-resistant Oxford nylon backpack with hidden zipper pockets, external USB charging port, and 180° flat opening luggage strap.",
            specifications={"Laptop Compartment": "Fits up to 15.6 inch laptops", "Capacity": "28 Liters", "Material": "Waterproof 900D Oxford Fabric", "Features": "Anti-theft lock, USB Port"},
            tags=["backpack", "bag", "laptop bag", "waterproof", "office"],
            priority=2
        )
        prod_diffuser = Product(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            title="Aroma Ultrasonic Essential Oil Diffuser (500ml)",
            slug="aroma-ultrasonic-essential-oil-diffuser-500ml",
            category="Home",
            sku="SKU-HOME-12",
            unit_price=1950.0,
            selling_price=1450.0,
            stock_quantity=50,
            stock_status="in_stock",
            images=["https://images.unsplash.com/photo-1608571423902-eed4a5ad8108?w=600&auto=format&fit=crop&q=80"],
            description="Whisper-quiet 500ml ultrasonic cool mist humidifier and aroma diffuser with 7-color soothing LED mood lights and auto-shutoff timer.",
            specifications={"Capacity": "500ml Water Tank", "Timer": "1h / 3h / 6h / Continuous", "Lighting": "7-Color Ambient LED", "Coverage": "Up to 300 sq. ft."},
            tags=["diffuser", "aroma", "humidifier", "home", "relaxation"],
            priority=2
        )
        prod_flask = Product(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            title="Double-Wall Vacuum Insulated Thermal Flask (1L)",
            slug="double-wall-vacuum-insulated-thermal-flask-1l",
            category="Home",
            sku="SKU-HOME-13",
            unit_price=1750.0,
            selling_price=1350.0,
            stock_quantity=40,
            stock_status="in_stock",
            images=["https://images.unsplash.com/photo-1602143407151-7111542de6e8?w=600&auto=format&fit=crop&q=80"],
            description="Food-grade 304 stainless steel thermal bottle keeping beverages hot for 18 hours or ice-cold for 24 hours with leak-proof cap.",
            specifications={"Capacity": "1000ml (1 Liter)", "Material": "18/8 Pro-Grade Stainless Steel", "Performance": "18h Hot / 24h Cold", "BPA Free": "Yes"},
            tags=["flask", "bottle", "thermal", "water bottle", "travel"],
            priority=1
        )
        prod_wallet = Product(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            title="Premium Full-Grain RFID Leather Wallet",
            slug="premium-full-grain-rfid-leather-wallet",
            category="Accessories",
            sku="SKU-ACC-14",
            unit_price=1950.0,
            selling_price=1550.0,
            stock_quantity=65,
            stock_status="in_stock",
            images=["https://images.unsplash.com/photo-1627123424574-724758594e93?w=600&auto=format&fit=crop&q=80"],
            description="Handmade oil-wax cowhide bi-fold wallet featuring 8 card slots, 2 currency compartments, and military-grade RFID blocking protection.",
            specifications={"Material": "100% Full-Grain Cowhide Leather", "Protection": "RFID Blocking 13.56 MHz", "Card Capacity": "Up to 10 Cards", "Color": "Vintage Brown"},
            tags=["wallet", "leather", "rfid", "accessories", "men"],
            priority=1
        )
        prod_keyboard = Product(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            title="Padma Mechanical RGB Gaming Keyboard",
            slug="padma-mechanical-rgb-gaming-keyboard",
            category="Electronics",
            sku="SKU-TECH-15",
            unit_price=4500.0,
            selling_price=3650.0,
            stock_quantity=28,
            stock_status="in_stock",
            images=["https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=600&auto=format&fit=crop&q=80"],
            description="Compact 75% hot-swappable mechanical keyboard with pre-lubed tactile switches, per-key RGB backlighting, and braided Type-C cable.",
            specifications={"Switches": "Hot-Swappable Blue / Brown Switches", "Layout": "75% ANSI (84 Keys)", "Backlight": "16.8M Color RGB (18 Modes)", "Keycaps": "Double-Shot PBT"},
            tags=["keyboard", "mechanical", "gaming", "rgb", "pc"],
            priority=1
        )

        padma_products = [
            prod_panjabi, prod_earbuds, prod_smartwatch, prod_saree, prod_polo,
            prod_kurti, prod_soundbar, prod_powerbank, prod_oxford, prod_sneakers,
            prod_backpack, prod_diffuser, prod_flask, prod_wallet, prod_keyboard
        ]
        db.add_all(padma_products)
        await db.flush()

        # 6c. Seed Orders into Orders Module
        order_1 = Order(
            id=uuid.uuid4(),
            order_number="ORD-20260818-8419",
            tenant_id=tenant.id,
            website_id=site_fashion.id,
            customer_name="Tanvir Ahmed",
            customer_phone="01711223344",
            customer_email="tanvir.ctg@example.com",
            delivery_address="House 12, Road 4, Dhanmondi",
            delivery_city="Dhaka",
            delivery_charge=60.0,
            items_json=[{
                "product_id": str(prod_panjabi.id),
                "title": prod_panjabi.title,
                "unit_price": 2490.0,
                "quantity": 1,
                "line_total": 2490.0,
                "selected_size": "XL (42)",
                "selected_color": "Royal Blue",
                "image_url": prod_panjabi.images[0]
            }],
            subtotal_amount=2490.0,
            total_amount=2550.0,
            payment_method="cash_on_delivery",
            payment_status="unpaid",
            order_status="confirmed",
            sms_sent=True,
            tracking_notes="Steadfast Express tracking: ST-99281"
        )
        order_2 = Order(
            id=uuid.uuid4(),
            order_number="ORD-20260818-9204",
            tenant_id=tenant.id,
            website_id=site_gadgets.id,
            customer_name="Imran Chowdhury",
            customer_phone="01812345678",
            customer_email="imran.ctg@gmail.com",
            delivery_address="Plot 5, Agrabad C/A",
            delivery_city="Chittagong",
            delivery_charge=120.0,
            items_json=[{
                "product_id": str(prod_smartwatch.id),
                "title": prod_smartwatch.title,
                "unit_price": 4800.0,
                "quantity": 1,
                "line_total": 4800.0,
                "selected_size": "Standard",
                "selected_color": "Black",
                "image_url": prod_smartwatch.images[0]
            }],
            subtotal_amount=4800.0,
            total_amount=4920.0,
            payment_method="bkash",
            payment_status="paid",
            bkash_trx_id="9X87KL22",
            order_status="shipped",
            sms_sent=True,
            tracking_notes="Pathao Courier: PTH-44819"
        )
        db.add_all([order_1, order_2])
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

        # 10. Seed Additional E-Commerce & ERP SaaS Tenants
        # Tenant 2: Apex Enterprise Solutions (ERP Client 1 - erpclient1@gmail.com for B2B / ERP Testing)
        t_apex = Tenant(
            id=uuid.uuid4(),
            name="Apex Enterprise Solutions",
            slug="apex-erp-cloud",
            business_category="erp",
            custom_domain="cloud.apexerp.example",
            whitelabel_enabled=True,
            branding_config={
                "brand_name": "Apex Cloud AI",
                "tagline": "Enterprise Resource Planning & B2B Solutions",
                "primary_color": "#0284C7"
            },
            enabled_modules={
                "dashboard": True, "inbox": True, "contacts": True,
                "products": False, "orders": False, "knowledge": True,
                "websites": True, "analytics": True, "usage": True,
                "team": True, "settings": True, "subscription": True
            }
        )
        db.add(t_apex)
        await db.flush()

        sub_apex = Subscription(
            tenant_id=t_apex.id,
            tier=SubscriptionTier.ENTERPRISE,
            status=SubscriptionStatus.ACTIVE,
            monthly_token_limit=10_000_000,
            monthly_conversation_limit=50_000,
            max_agents=20,
            max_websites=5,
            current_period_start=utc_now() - timedelta(days=7),
            current_period_end=utc_now() + timedelta(days=23)
        )
        db.add(sub_apex)

        u_apex = User(
            tenant_id=t_apex.id,
            email="erpclient1@gmail.com",
            hashed_password=get_password_hash("12345678"),
            full_name="ERP Client 1 (Apex Cloud)",
            role=UserRole.TENANT_OWNER,
            department="Executive",
            is_active=True
        )
        db.add(u_apex)

        asst_apex = AIAssistant(
            tenant_id=t_apex.id,
            name="Apex Enterprise Operations Bot",
            personality_type="technical",
            model_name="gemini-1.5-pro",
            system_instruction="You are Apex Enterprise Cloud's ERP specialist assistant. Assist corporate clients with billing, ledger synchronization, employee access, and supply chain ERP inquiries.",
            fallback_message="Connecting you with an Apex Enterprise ERP solution architect."
        )
        db.add(asst_apex)
        await db.flush()

        site_apex = Website(
            tenant_id=t_apex.id,
            assistant_id=asst_apex.id,
            name="Apex Cloud Portal",
            domain="portal.apexerp.example",
            widget_key=f"wg_erp_{uuid.uuid4().hex[:12]}",
            primary_color="#0284C7",
            header_title="Apex ERP Enterprise Support",
            welcome_message="Welcome to Apex ERP Cloud. How can we support your enterprise workflows today?",
            is_active=True
        )
        db.add(site_apex)
        await db.flush()

        # Tenant 3: Horizon Retail Ltd. (E-Commerce Client 2 - ecommerceclient2@gmail.com for Multi-Tenant Isolation)
        t_horizon = Tenant(
            id=uuid.uuid4(),
            name="Horizon Retail Ltd.",
            slug="horizon-retail",
            business_category="ecommerce",
            custom_domain="shop.horizonretail.com.bd",
            whitelabel_enabled=True,
            branding_config={
                "brand_name": "Horizon Smart Bot",
                "tagline": "Modern Office Tech & Workspace Ergonomics",
                "primary_color": "#059669"
            },
            enabled_modules={
                "dashboard": True, "inbox": True, "contacts": True,
                "products": True, "orders": True, "knowledge": True,
                "websites": True, "analytics": True, "usage": True,
                "team": True, "settings": True, "subscription": True
            },
            ecommerce_settings={
                "cod_enabled": True,
                "delivery_charge_inside_dhaka": 70.0,
                "delivery_charge_outside_dhaka": 130.0
            }
        )
        db.add(t_horizon)
        await db.flush()

        sub_horizon = Subscription(
            tenant_id=t_horizon.id,
            tier=SubscriptionTier.GROWTH,
            status=SubscriptionStatus.ACTIVE,
            monthly_token_limit=5_000_000,
            monthly_conversation_limit=25_000,
            max_agents=10,
            max_websites=3,
            current_period_start=utc_now() - timedelta(days=5),
            current_period_end=utc_now() + timedelta(days=25)
        )
        db.add(sub_horizon)

        u_horizon = User(
            tenant_id=t_horizon.id,
            email="ecommerceclient2@gmail.com",
            hashed_password=get_password_hash("12345678"),
            full_name="E-Commerce Client 2 (Horizon Store)",
            role=UserRole.TENANT_OWNER,
            department="Executive",
            is_active=True
        )
        db.add(u_horizon)

        asst_horizon = AIAssistant(
            tenant_id=t_horizon.id,
            name="Horizon Workspace Assistant",
            personality_type="friendly",
            model_name="gemini-1.5-flash",
            system_instruction="You are Horizon Retail's smart assistant for ergonomics and office tech products in Bangladesh.",
            fallback_message="Let me connect you with Horizon support team."
        )
        db.add(asst_horizon)
        await db.flush()

        site_horizon = Website(
            tenant_id=t_horizon.id,
            assistant_id=asst_horizon.id,
            name="Horizon Office & Tech Store",
            domain="horizonretail.com.bd",
            widget_key=f"wg_horizon_{uuid.uuid4().hex[:12]}",
            primary_color="#059669",
            header_title="Horizon Tech Live Chat",
            welcome_message="Welcome to Horizon Retail! Need ergonomic workspace setups or tech accessories?",
            is_active=True
        )
        db.add(site_horizon)
        await db.flush()

        # Seed Distinct Products ONLY for client2@gmail.com (Horizon Retail)
        prod_hz_chair = Product(
            id=uuid.uuid4(),
            tenant_id=t_horizon.id,
            title="Horizon Ergonomic High-Back Mesh Chair",
            slug="horizon-ergonomic-high-back-mesh-chair",
            category="Office",
            sku="SKU-HRZ-CHR-01",
            unit_price=16500.0,
            selling_price=13900.0,
            stock_quantity=25,
            stock_status="in_stock",
            images=["https://images.unsplash.com/photo-1580481077195-731da96f7477?w=600&auto=format&fit=crop&q=80"],
            description="Premium Korean breathable mesh ergonomic executive chair with 3D adjustable armrests, adaptive lumbar support, and 135-degree recline.",
            specifications={"Material": "Korean Breathable Mesh", "Mechanism": "Synchronized Multi-Lock Tilt", "Weight Capacity": "150 KG", "Warranty": "2 Years Manufacturer"},
            tags=["chair", "office", "ergonomic", "mesh", "furniture"],
            priority=10
        )
        prod_hz_stand = Product(
            id=uuid.uuid4(),
            tenant_id=t_horizon.id,
            title="Horizon Pro Dual-Monitor Aluminum Gas Spring Arm",
            slug="horizon-pro-dual-monitor-aluminum-gas-spring-arm",
            category="Office",
            sku="SKU-HRZ-ARM-02",
            unit_price=5200.0,
            selling_price=4200.0,
            stock_quantity=40,
            stock_status="in_stock",
            images=["https://images.unsplash.com/photo-1527443224154-c4a3942d3acf?w=600&auto=format&fit=crop&q=80"],
            description="Heavy-duty aircraft-grade aluminum dual monitor arm holding two 17\" to 32\" displays with full 360-degree rotation and integrated cable management.",
            specifications={"VESA Compatibility": "75x75mm, 100x100mm", "Screen Sizes": "17\" - 32\" per arm", "Weight Limit": "9 KG per arm"},
            tags=["monitor arm", "desk setup", "dual monitor", "accessories"],
            priority=9
        )
        prod_hz_dripper = Product(
            id=uuid.uuid4(),
            tenant_id=t_horizon.id,
            title="Horizon Minimalist Matte Black Pour-Over Dripper Set",
            slug="horizon-minimalist-matte-black-pour-over-dripper-set",
            category="Lifestyle",
            sku="SKU-HRZ-DRP-03",
            unit_price=2200.0,
            selling_price=1750.0,
            stock_quantity=30,
            stock_status="in_stock",
            images=["https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?w=600&auto=format&fit=crop&q=80"],
            description="Handcrafted ceramic V60 pour-over coffee brewer set with 600ml borosilicate glass server and heat-resistant wooden collar.",
            specifications={"Material": "Ceramic + Borosilicate Heatproof Glass", "Capacity": "600ml (1-4 Cups)", "Color": "Matte Charcoal Black"},
            tags=["coffee", "dripper", "lifestyle", "ceramic", "kitchen"],
            priority=8
        )
        prod_hz_mouse = Product(
            id=uuid.uuid4(),
            tenant_id=t_horizon.id,
            title="Horizon Wireless Vertical Ergonomic Mouse",
            slug="horizon-wireless-vertical-ergonomic-mouse",
            category="Electronics",
            sku="SKU-HRZ-MSE-04",
            unit_price=2900.0,
            selling_price=2350.0,
            stock_quantity=55,
            stock_status="in_stock",
            images=["https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7?w=600&auto=format&fit=crop&q=80"],
            description="57-degree natural handshake posture wireless ergonomic mouse with silent optical clicks, dual Bluetooth 5.0 + 2.4GHz USB receiver, and rechargeable battery.",
            specifications={"Connectivity": "Bluetooth 5.0 + 2.4G Wireless", "DPI Levels": "800 / 1200 / 1600 / 2400 DPI", "Battery": "500mAh Rechargeable (3 Months)"},
            tags=["mouse", "ergonomic", "wireless", "office", "electronics"],
            priority=7
        )
        db.add_all([prod_hz_chair, prod_hz_stand, prod_hz_dripper, prod_hz_mouse])
        await db.flush()

        # Tenant 3: Daraz Seller Hub BD (Enterprise Tier)
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
            hashed_password=get_password_hash("12345678"),
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
            hashed_password=get_password_hash("12345678"),
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
            hashed_password=get_password_hash("12345678"),
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
            hashed_password=get_password_hash("12345678"),
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

        # Seed In-App Real-Time Notifications
        notif1 = Notification(
            tenant_id=tenant.id,
            title="🛒 New Order #ORD-8921 Placed",
            message="New order for ৳3,450.00 (Padma Ultra Watch + Panjabi) placed by Sadia Rahman via bKash Online.",
            type="order",
            is_read=False,
            link="/orders",
            created_at=utc_now() - timedelta(minutes=12)
        )
        notif2 = Notification(
            tenant_id=tenant.id,
            title="🚨 Human Agent Handover Requested",
            message="Customer Farhan (+8801712345678) requested human assistance in Live Chat queue.",
            type="handover",
            is_read=False,
            link="/inbox",
            created_at=utc_now() - timedelta(minutes=45)
        )
        notif3 = Notification(
            tenant_id=tenant.id,
            title="🧠 RAG Knowledge Base Indexed",
            message="'Padma Mart Delivery & Payment Policy 2026.pdf' successfully vectorized into 142 embeddings.",
            type="knowledge",
            is_read=False,
            link="/knowledge",
            created_at=utc_now() - timedelta(hours=2)
        )
        notif4 = Notification(
            tenant_id=tenant.id,
            title="⚡ Token Quota Update",
            message="You have consumed 1.86M of 10.0M monthly AI tokens (81.4% capacity remaining).",
            type="billing",
            is_read=True,
            link="/subscription",
            created_at=utc_now() - timedelta(hours=5)
        )
        db.add_all([notif1, notif2, notif3, notif4])

        await db.commit()
        print("[SUCCESS] E-Commerce Database Seeding Successfully Completed (Bangladeshi Format + BDT Taka)!")

if __name__ == "__main__":
    asyncio.run(seed_database())
