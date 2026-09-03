import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import jwt, JWTError

from app.core.database import get_db
from app.core.config import settings
from app.core.security import verify_password, get_password_hash, create_access_token, create_refresh_token
from app.models.all_models import User, Tenant, Subscription, SubscriptionTier, SubscriptionStatus, UserRole, Website, AIAssistant
from app.schemas.schemas import UserRegister, UserLogin, TokenResponse, UserOut, TenantProvisionRequest

router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()
security_optional = HTTPBearer(auto_error=False)

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            raise HTTPException(status_code=401, detail="Invalid token subject")
        user_id = uuid.UUID(user_id_str)
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Could not validate credentials")

    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Connect Super Admin to Platform Live Support Chatbot Tenant
    if user.role == UserRole.SUPER_ADMIN and not user.tenant_id:
        w_stmt = select(Website).where(Website.widget_key == "wgt_platform_live_support")
        w_res = await db.execute(w_stmt)
        w = w_res.scalars().first()
        if w:
            user.tenant_id = w.tenant_id
            await db.commit()
            await db.refresh(user)

    return user

async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    if not credentials:
        return None
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id_str: str = payload.get("sub")
        if not user_id_str:
            return None
        user_id = uuid.UUID(user_id_str)
        result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
        return result.scalars().first()
    except Exception:
        return None

@router.post("/register", response_model=TokenResponse)
async def register(payload: UserRegister, db: AsyncSession = Depends(get_db)):
    # 1. Check if email already exists
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Email already registered")

    # 2. Create Tenant
    slug = payload.tenant_name.lower().replace(" ", "-") + f"-{uuid.uuid4().hex[:6]}"
    tenant = Tenant(
        name=payload.tenant_name,
        slug=slug
    )
    db.add(tenant)
    await db.flush()

    # 3. Assign Default Free Subscription
    subscription = Subscription(
        tenant_id=tenant.id,
        tier=SubscriptionTier.FREE,
        status=SubscriptionStatus.ACTIVE
    )
    db.add(subscription)

    # 4. Create Tenant Owner User
    user = User(
        tenant_id=tenant.id,
        email=payload.email,
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name,
        role=UserRole.TENANT_OWNER,
        is_verified=True
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # 5. Generate Tokens
    access_token = create_access_token(
        subject=str(user.id),
        extra_claims={"tenant_id": str(tenant.id), "role": user.role.value}
    )
    refresh_token = create_refresh_token(subject=str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=user.id,
        tenant_id=tenant.id,
        role=user.role,
        full_name=user.full_name
    )

@router.post("/provision-tenant", response_model=TokenResponse)
async def provision_new_tenant(payload: TenantProvisionRequest, db: AsyncSession = Depends(get_db)):
    """
    Public Self-Serve Package Purchase & Onboarding:
    - Creates Organization / Tenant in PostgreSQL
    - Assigns selected Subscription Tier (Starter / Growth / Enterprise) with token limits
    - Creates Organization Owner user
    - Provisions default AI Assistant & Website Chat Widget
    - Returns instant JWT tokens
    """
    # 1. Check existing email
    existing_user = await db.execute(select(User).where(User.email == payload.admin_email))
    if existing_user.scalars().first():
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    # 2. Create Tenant with Category-Specific Modules
    slug = payload.organization_name.lower().replace(" ", "-").replace(".", "")[:30] + f"-{uuid.uuid4().hex[:6]}"
    category = payload.business_category.lower() if payload.business_category else "ecommerce"
    
    if category == "erp":
        enabled_modules = {
            "dashboard": True, "inbox": True, "contacts": True,
            "products": False, "orders": False, "knowledge": True,
            "websites": True, "analytics": True, "usage": True,
            "team": True, "settings": True, "subscription": True
        }
        assistant_instruction = f"You are the official Enterprise AI Assistant for {payload.organization_name}. You specialize in enterprise business support, SLA tickets, customer inquiries, meeting scheduling, and corporate knowledge documentation."
    elif category == "services":
        enabled_modules = {
            "dashboard": True, "inbox": True, "contacts": True,
            "products": False, "orders": False, "knowledge": True,
            "websites": True, "analytics": True, "usage": True,
            "team": True, "settings": True, "subscription": True
        }
        assistant_instruction = f"You are the official Consulting & Service AI Assistant for {payload.organization_name}. Assist clients with consultation bookings, service inquiries, and project FAQs."
    else:
        # Default E-Commerce
        category = "ecommerce"
        enabled_modules = {
            "dashboard": True, "inbox": True, "contacts": True,
            "products": True, "orders": True, "knowledge": True,
            "websites": True, "analytics": True, "usage": True,
            "team": True, "settings": True, "subscription": True
        }
        assistant_instruction = f"You are {payload.organization_name}'s smart E-Commerce Shopping Assistant. Help customers find products, select sizes, track delivery, and place orders via bKash COD."

    tenant = Tenant(
        name=payload.organization_name,
        slug=slug,
        business_category=category,
        is_active=True,
        whitelabel_enabled=(payload.subscription_tier == SubscriptionTier.ENTERPRISE),
        branding_config={"brand_name": payload.organization_name, "primary_color": "#4F46E5"},
        enabled_modules=enabled_modules
    )
    db.add(tenant)
    await db.flush()

    # 3. Provision Subscription Tier with exact quotas
    tier_configs = {
        SubscriptionTier.FREE: {"tokens": 50_000, "agents": 1, "websites": 1},
        SubscriptionTier.STARTER: {"tokens": 500_000, "agents": 2, "websites": 1},
        SubscriptionTier.GROWTH: {"tokens": 2_500_000, "agents": 10, "websites": 5},
        SubscriptionTier.ENTERPRISE: {"tokens": 10_000_000, "agents": 25, "websites": 20}
    }
    config = tier_configs.get(payload.subscription_tier, tier_configs[SubscriptionTier.STARTER])

    sub = Subscription(
        tenant_id=tenant.id,
        tier=payload.subscription_tier,
        status=SubscriptionStatus.ACTIVE,
        monthly_token_limit=config["tokens"],
        max_agents=config["agents"],
        max_websites=config["websites"],
        monthly_conversation_limit=1000
    )
    db.add(sub)

    # 4. Create Organization Owner
    owner = User(
        tenant_id=tenant.id,
        email=payload.admin_email,
        hashed_password=get_password_hash(payload.password),
        full_name=payload.admin_name,
        role=UserRole.TENANT_OWNER,
        department="Executive",
        is_active=True
    )
    db.add(owner)
    await db.flush()

    # 5. Provision Default AI Assistant
    assistant = AIAssistant(
        tenant_id=tenant.id,
        name=f"{payload.organization_name} Assistant",
        description=f"Primary {category.upper()} AI assistant",
        model_name="gemini-1.5-flash",
        temperature=0.3,
        system_instruction=assistant_instruction,
        fallback_message="I am connecting you with our human support team.",
        auto_handover_keywords=["agent", "human", "help", "support", "talk to human"]
    )
    db.add(assistant)
    await db.flush()

    # 6. Provision Default Live Chat Widget
    widget_key = f"wgt_{uuid.uuid4().hex[:18]}"
    website = Website(
        tenant_id=tenant.id,
        assistant_id=assistant.id,
        widget_key=widget_key,
        name=f"{payload.organization_name} Main Portal",
        domain=f"{slug}.example.com",
        header_title=f"{payload.organization_name} Live AI",
        welcome_message="Hello! How can we assist your business today?",
        primary_color="#4F46E5"
    )
    db.add(website)

    await db.commit()
    await db.refresh(owner)

    # 7. Generate JWT Tokens
    access_token = create_access_token(
        subject=str(owner.id),
        extra_claims={"tenant_id": str(tenant.id), "role": owner.role.value}
    )
    refresh_token = create_refresh_token(subject=str(owner.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=owner.id,
        tenant_id=tenant.id,
        role=owner.role,
        full_name=owner.full_name
    )

@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalars().first()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    # Connect Super Admin to Platform Live Support Chatbot Tenant
    if user.role == UserRole.SUPER_ADMIN and not user.tenant_id:
        w_stmt = select(Website).where(Website.widget_key == "wgt_platform_live_support")
        w_res = await db.execute(w_stmt)
        w = w_res.scalars().first()
        if w:
            user.tenant_id = w.tenant_id
            await db.commit()
            await db.refresh(user)

    access_token = create_access_token(
        subject=str(user.id),
        extra_claims={"tenant_id": str(user.tenant_id) if user.tenant_id else None, "role": user.role.value}
    )
    refresh_token = create_refresh_token(subject=str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        full_name=user.full_name
    )

@router.get("/me", response_model=UserOut)
async def get_current_user_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from app.services.tenant.module_service import TenantModuleService
    from app.models.all_models import Tenant

    modules_map = None
    t_name = None
    if user.tenant_id:
        stmt = select(Tenant).where(Tenant.id == user.tenant_id)
        tenant = (await db.execute(stmt)).scalars().first()
        if tenant:
            modules_map = TenantModuleService.resolve_tenant_modules(tenant)
            t_name = tenant.name

    return UserOut(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        department=user.department,
        is_active=user.is_active,
        is_online=user.is_online,
        avatar_url=user.avatar_url,
        enabled_modules=modules_map,
        tenant_name=t_name,
        created_at=user.created_at
    )
