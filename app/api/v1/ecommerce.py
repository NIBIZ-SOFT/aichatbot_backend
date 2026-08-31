import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.core.security import encrypt_secret, decrypt_secret
from app.models.all_models import User, Tenant, Product, Order
from app.schemas.schemas import (
    ProductCreate, ProductUpdate, ProductOut, ProductGenerateTagsRequest, ProductGenerateTagsResponse,
    OrderCreate, OrderStatusUpdate, OrderOut,
    EcommerceSettingsOut, EcommerceSettingsUpdate, TestSMSRequest
)
from app.services.ecommerce.product_service import ProductService
from app.services.ecommerce.order_service import OrderService
from app.services.sms.sms_service import SMSService

router = APIRouter(tags=["Conversational E-Commerce & Inventory Operations"])

# ----------------- MASTER TENANT SUSPENSION KILL-SWITCH DEPENDENCY -----------------
async def require_active_tenant(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Tenant:
    """
    Enforces the Master Suspension Kill-Switch.
    If an organization is marked as suspended by Super Admin, all mutations are blocked.
    """
    tenant = await db.get(Tenant, user.tenant_id)
    if not tenant or not tenant.is_active:
        raise HTTPException(
            status_code=403,
            detail="Organization account is currently suspended. All modifications and order creation are locked. Please contact platform support."
        )
    return tenant

# ----------------- PRODUCT CATALOG ENDPOINTS -----------------

@router.get("/products", response_model=List[ProductOut])
async def list_products(
    category: Optional[str] = None,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    sort_by: Optional[str] = Query(None, description="title | selling_price | stock_quantity | priority | created_at"),
    sort_dir: Optional[str] = Query("desc", description="asc or desc"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    service = ProductService(db)
    return await service.get_products(
        tenant_id=user.tenant_id,
        category=category,
        search=search,
        is_active=is_active,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset
    )

@router.post("/products", response_model=ProductOut, status_code=201)
async def create_product(
    data: ProductCreate,
    tenant: Tenant = Depends(require_active_tenant),
    db: AsyncSession = Depends(get_db)
):
    service = ProductService(db)
    return await service.create_product(tenant_id=tenant.id, data=data)

@router.put("/products/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: uuid.UUID,
    data: ProductUpdate,
    tenant: Tenant = Depends(require_active_tenant),
    db: AsyncSession = Depends(get_db)
):
    service = ProductService(db)
    product = await service.update_product(product_id=product_id, tenant_id=tenant.id, data=data)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@router.delete("/products/{product_id}")
async def delete_product(
    product_id: uuid.UUID,
    tenant: Tenant = Depends(require_active_tenant),
    db: AsyncSession = Depends(get_db)
):
    service = ProductService(db)
    success = await service.delete_product(product_id=product_id, tenant_id=tenant.id)
    if not success:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"status": "success", "message": "Product and vector knowledge chunk removed."}


@router.patch("/products/{product_id}/priority", response_model=ProductOut)
@router.put("/products/{product_id}/priority", response_model=ProductOut)
async def set_product_priority(
    product_id: uuid.UUID,
    priority: int = Query(..., ge=0, description="New priority rank (1=highest, 0=unranked). Auto-shifts others."),
    tenant: Tenant = Depends(require_active_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Set product display priority for CDN widget catalog ordering.
    Priority 1 = shown first. Auto-shifts other products to maintain a clean,
    non-duplicate ranked sequence (Smart Cascade Reorder Engine).
    Setting priority=0 removes the product from the ranked list.
    """
    service = ProductService(db)
    product = await service.update_product(
        product_id=product_id,
        tenant_id=tenant.id,
        data=ProductUpdate(priority=priority)
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("/products/normalize-priorities")
async def normalize_product_priorities(
    tenant: Tenant = Depends(require_active_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Tenant-Scoped Priority Normalization:
    Ensures all ranked products for the tenant form a clean, gapless 1..N sequence.
    """
    service = ProductService(db)
    await service.normalize_priorities(tenant.id)
    await db.commit()
    return {"status": "success", "message": "Tenant product priorities normalized to gapless 1-indexed sequence."}


@router.post("/products/generate-tags", response_model=ProductGenerateTagsResponse)
async def generate_product_tags(
    data: ProductGenerateTagsRequest,
    tenant: Tenant = Depends(require_active_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    On-demand AI Auto-Tagger endpoint for dashboard product creation/editing preview.
    Analyzes title, category, description, and specs to produce multilingual search keywords.
    """
    service = ProductService(db)
    tags = await service.generate_ai_tags(
        title=data.title,
        category=data.category or "General",
        description=data.description or "",
        specifications=data.specifications or {}
    )
    return ProductGenerateTagsResponse(tags=tags)

# ----------------- ORDER MANAGEMENT ENDPOINTS -----------------

@router.get("/orders", response_model=List[OrderOut])
async def list_orders(
    status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    service = OrderService(db)
    return await service.get_orders(
        tenant_id=user.tenant_id,
        status=status,
        search=search,
        limit=limit,
        offset=offset
    )

@router.get("/orders/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Order).where(Order.id == order_id, Order.tenant_id == user.tenant_id)
    res = await db.execute(stmt)
    order = res.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@router.patch("/orders/{order_id}/status", response_model=OrderOut)
async def update_order_status(
    order_id: uuid.UUID,
    data: OrderStatusUpdate,
    tenant: Tenant = Depends(require_active_tenant),
    db: AsyncSession = Depends(get_db)
):
    service = OrderService(db)
    order = await service.update_order_status(order_id=order_id, tenant_id=tenant.id, data=data)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@router.post("/orders/{order_id}/resend-sms")
async def resend_order_sms(
    order_id: uuid.UUID,
    tenant: Tenant = Depends(require_active_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually triggers re-sending of the order confirmation SMS to customer mobile.
    """
    service = OrderService(db)
    result = await service.resend_order_sms(order_id=order_id, tenant_id=tenant.id)
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("message", "Order not found"))
    return result

# ----------------- ECOMMERCE & GATEWAY SETTINGS -----------------

@router.get("/tenant/ecommerce-settings", response_model=EcommerceSettingsOut)
async def get_ecommerce_settings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    tenant = await db.get(Tenant, user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    settings = tenant.ecommerce_settings or {}
    bkash_cfg = settings.get("bkash", {})
    eps_cfg = settings.get("eps", {})
    sms_cfg = settings.get("sms", {})

    app_key = bkash_cfg.get("app_key", "")
    masked_app_key = f"{app_key[:4]}...{app_key[-4:]}" if len(app_key) > 8 else ("Configured" if app_key else None)
    
    sender_id = sms_cfg.get("sender_id", "")
    masked_sender = sender_id if sender_id else None

    sms_key = sms_cfg.get("api_key", "")
    masked_sms_key = f"{sms_key[:4]}...{sms_key[-4:]}" if len(sms_key) > 8 else ("Configured" if sms_key else None)

    eps_m_id = eps_cfg.get("merchant_id", "")
    masked_eps_m_id = f"{eps_m_id[:4]}...{eps_m_id[-4:]}" if len(eps_m_id) > 8 else ("Configured" if eps_m_id else None)

    eps_s_id = eps_cfg.get("store_id", "")
    masked_eps_s_id = f"{eps_s_id[:4]}...{eps_s_id[-4:]}" if len(eps_s_id) > 8 else ("Configured" if eps_s_id else None)

    return {
        "business_category": tenant.business_category or "ecommerce",
        "cod_enabled": settings.get("cod_enabled", True),
        "bkash_enabled": bkash_cfg.get("enabled", False),
        "bkash_is_sandbox": bkash_cfg.get("is_sandbox", True),
        "bkash_base_url": bkash_cfg.get("base_url", "https://tokenized.sandbox.bka.sh/v1.2.0-beta"),
        "bkash_app_key_masked": masked_app_key,
        "bkash_username_masked": bkash_cfg.get("username"),
        "eps_enabled": eps_cfg.get("enabled", False),
        "eps_is_sandbox": eps_cfg.get("is_sandbox", True),
        "eps_base_url": eps_cfg.get("base_url", "https://sandboxpgapi.eps.com.bd"),
        "eps_username_masked": eps_cfg.get("username"),
        "eps_merchant_id_masked": masked_eps_m_id,
        "eps_store_id_masked": masked_eps_s_id,
        "eps_merchant_number": eps_cfg.get("merchant_number"),
        "delivery_charge_inside_dhaka": settings.get("delivery_charge_inside_dhaka", 60.0),
        "delivery_charge_outside_dhaka": settings.get("delivery_charge_outside_dhaka", 120.0),
        "sms_notifications_enabled": sms_cfg.get("enabled", True),
        "sms_provider": sms_cfg.get("provider", "smsmatrix"),
        "sms_sender_id_masked": masked_sender,
        "sms_api_key_masked": masked_sms_key,
        "sms_order_template": settings.get("sms_order_template")
    }

@router.put("/tenant/ecommerce-settings", response_model=EcommerceSettingsOut)
async def update_ecommerce_settings(
    data: EcommerceSettingsUpdate,
    tenant: Tenant = Depends(require_active_tenant),
    db: AsyncSession = Depends(get_db)
):
    settings = dict(tenant.ecommerce_settings or {})
    bkash_cfg = dict(settings.get("bkash", {}))
    eps_cfg = dict(settings.get("eps", {}))
    sms_cfg = dict(settings.get("sms", {}))

    if data.business_category is not None:
        tenant.business_category = data.business_category
    if data.cod_enabled is not None:
        settings["cod_enabled"] = data.cod_enabled
    if data.delivery_charge_inside_dhaka is not None:
        settings["delivery_charge_inside_dhaka"] = data.delivery_charge_inside_dhaka
    if data.delivery_charge_outside_dhaka is not None:
        settings["delivery_charge_outside_dhaka"] = data.delivery_charge_outside_dhaka
    if data.sms_order_template is not None:
        settings["sms_order_template"] = data.sms_order_template

    # Tenant-Scoped bKash Settings
    if data.bkash_enabled is not None:
        bkash_cfg["enabled"] = data.bkash_enabled
    if data.bkash_is_sandbox is not None:
        bkash_cfg["is_sandbox"] = data.bkash_is_sandbox
    if data.bkash_base_url is not None:
        bkash_cfg["base_url"] = data.bkash_base_url
    if data.bkash_app_key is not None:
        bkash_cfg["app_key"] = data.bkash_app_key
    if data.bkash_username is not None:
        bkash_cfg["username"] = data.bkash_username
    if data.bkash_app_secret:
        bkash_cfg["encrypted_app_secret"] = encrypt_secret(data.bkash_app_secret)
    if data.bkash_password:
        bkash_cfg["encrypted_password"] = encrypt_secret(data.bkash_password)

    # Tenant-Scoped EPS Settings
    if data.eps_enabled is not None:
        eps_cfg["enabled"] = data.eps_enabled
    if data.eps_is_sandbox is not None:
        eps_cfg["is_sandbox"] = data.eps_is_sandbox
    if data.eps_base_url is not None:
        eps_cfg["base_url"] = data.eps_base_url
    if data.eps_username is not None:
        eps_cfg["username"] = data.eps_username
    if data.eps_merchant_id is not None:
        eps_cfg["merchant_id"] = data.eps_merchant_id
    if data.eps_store_id is not None:
        eps_cfg["store_id"] = data.eps_store_id
    if data.eps_merchant_number is not None:
        eps_cfg["merchant_number"] = data.eps_merchant_number
    if data.eps_password:
        eps_cfg["encrypted_password"] = encrypt_secret(data.eps_password)
    if data.eps_hash_key:
        eps_cfg["encrypted_hash_key"] = encrypt_secret(data.eps_hash_key)

    # SMS Settings
    if data.sms_notifications_enabled is not None:
        sms_cfg["enabled"] = data.sms_notifications_enabled
    if data.sms_provider is not None:
        sms_cfg["provider"] = data.sms_provider
    if data.sms_sender_id is not None:
        sms_cfg["sender_id"] = data.sms_sender_id
    if data.sms_api_key:
        sms_cfg["api_key"] = data.sms_api_key

    settings["bkash"] = bkash_cfg
    settings["eps"] = eps_cfg
    settings["sms"] = sms_cfg
    tenant.ecommerce_settings = settings

    await db.commit()
    await db.refresh(tenant)

    app_key = bkash_cfg.get("app_key", "")
    masked_app_key = f"{app_key[:4]}...{app_key[-4:]}" if len(app_key) > 8 else ("Configured" if app_key else None)

    sms_key = sms_cfg.get("api_key", "")
    masked_sms_key = f"{sms_key[:4]}...{sms_key[-4:]}" if len(sms_key) > 8 else ("Configured" if sms_key else None)

    eps_m_id = eps_cfg.get("merchant_id", "")
    masked_eps_m_id = f"{eps_m_id[:4]}...{eps_m_id[-4:]}" if len(eps_m_id) > 8 else ("Configured" if eps_m_id else None)

    eps_s_id = eps_cfg.get("store_id", "")
    masked_eps_s_id = f"{eps_s_id[:4]}...{eps_s_id[-4:]}" if len(eps_s_id) > 8 else ("Configured" if eps_s_id else None)

    return {
        "business_category": tenant.business_category or "ecommerce",
        "cod_enabled": settings.get("cod_enabled", True),
        "bkash_enabled": bkash_cfg.get("enabled", False),
        "bkash_is_sandbox": bkash_cfg.get("is_sandbox", True),
        "bkash_base_url": bkash_cfg.get("base_url", "https://tokenized.sandbox.bka.sh/v1.2.0-beta"),
        "bkash_app_key_masked": masked_app_key,
        "bkash_username_masked": bkash_cfg.get("username"),
        "eps_enabled": eps_cfg.get("enabled", False),
        "eps_is_sandbox": eps_cfg.get("is_sandbox", True),
        "eps_base_url": eps_cfg.get("base_url", "https://sandboxpgapi.eps.com.bd"),
        "eps_username_masked": eps_cfg.get("username"),
        "eps_merchant_id_masked": masked_eps_m_id,
        "eps_store_id_masked": masked_eps_s_id,
        "eps_merchant_number": eps_cfg.get("merchant_number"),
        "delivery_charge_inside_dhaka": settings.get("delivery_charge_inside_dhaka", 60.0),
        "delivery_charge_outside_dhaka": settings.get("delivery_charge_outside_dhaka", 120.0),
        "sms_notifications_enabled": sms_cfg.get("enabled", True),
        "sms_provider": sms_cfg.get("provider", "smsmatrix"),
        "sms_sender_id_masked": sms_cfg.get("sender_id"),
        "sms_api_key_masked": masked_sms_key,
        "sms_order_template": settings.get("sms_order_template")
    }

@router.post("/tenant/ecommerce-settings/test-sms")
async def test_sms_gateway(
    data: TestSMSRequest,
    tenant: Tenant = Depends(require_active_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Sends a test SMS to verify the configured SMS Gateway and API Key in real time.
    """
    sms_cfg = (tenant.ecommerce_settings or {}).get("sms", {})
    if not sms_cfg.get("api_key") and not sms_cfg.get("enabled"):
        raise HTTPException(status_code=400, detail="SMS gateway is not enabled or API key is missing.")

    msg = data.message or f"Hello from {tenant.name}! Your automated SMS Gateway configuration is active and working."
    res = await SMSService.send_order_sms(
        phone_number=data.phone_number,
        message_text=msg,
        sms_config=sms_cfg
    )
    return res
