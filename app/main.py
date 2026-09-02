import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.core.database import engine, Base
from app.api.v1.router import api_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB schemas on startup & ensure dynamic columns
    from sqlalchemy import text
    from app.core.database import AsyncSessionLocal
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

    # Auto-seed check: if Super Admin is missing, automatically initialize and seed database
    try:
        async with AsyncSessionLocal() as session:
            admin_check = await session.execute(text("SELECT id FROM users WHERE email = 'admin@gmail.com' LIMIT 1;"))
            if not admin_check.scalar_one_or_none():
                print("[AUTO-SEED] Super Admin account not found. Automatically initializing and seeding database on startup...")
                from app.seed import seed_database
                await seed_database()
                print("[AUTO-SEED] Startup seeding completed successfully!")
    except Exception as e:
        print(f"[AUTO-SEED WARNING] Startup seeder check skipped: {str(e)}")

    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Jobab Chat — Enterprise Customer Communication & AI Agent Platform API",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Disable caching for static files in development
@app.middleware("http")
async def add_no_cache_header(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Mount API routes
app.include_router(api_router, prefix=settings.API_V1_STR)

# Mount Static directory for embeddable widget.js & demo pages
static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": "1.0.0-production",
        "health": "/health",
        "version_endpoint": "/version",
        "seed_database": "/seed-db",
        "docs": f"{settings.API_V1_STR}/docs",
        "api_v1": f"{settings.API_V1_STR}",
        "widget_script": "/static/widget.js",
        "demo_page": "/static/demo.html"
    }

@app.get("/version")
async def version_check():
    from datetime import datetime, timezone
    from app.services.ai.gemini import gemini_service
    return {
        "service": settings.PROJECT_NAME,
        "version": "1.0.0-production",
        "environment": settings.ENVIRONMENT,
        "active_ai_model": gemini_service.model or "google/gemini-2.5-flash",
        "ai_gateway": "OpenRouter AI Universal Gateway",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "re-deployed_and_online"
    }

@app.get("/health")
@app.get("/api/v1/health")
async def health_check():
    """
    Production health check endpoint verifying FastAPI process & PostgreSQL DB connection.
    """
    from sqlalchemy import text
    from datetime import datetime, timezone
    db_status = "connected"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1;"))
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "healthy" if db_status == "connected" else "unhealthy",
        "database": db_status,
        "service": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/seed-db")
@app.get("/api/v1/seed-db")
async def run_database_seed():
    """
    Trigger database schema creation & demo seeding via direct HTTP GET request.
    """
    try:
        import importlib
        import app.seed
        importlib.reload(app.seed)
        await app.seed.seed_database()
        return {
            "status": "success",
            "message": "Jobab Chat Platform successfully initialized and production-seeded!",
            "infrastructure": {
                "super_admin": {
                    "email": "admin@gmail.com",
                    "role": "SUPER_ADMIN"
                },
                "ai_gateway": "OpenRouter Universal AI Gateway (google/gemini-2.5-flash)",
                "payment_gateways": "bKash Tokenized Checkout & EPS Multi-Channel PGW",
                "saas_plans": ["Free", "Starter", "Growth", "Enterprise"],
                "coupons": ["WELCOME50", "LAUNCH2026"]
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Seeder error: {str(e)}"
        }

