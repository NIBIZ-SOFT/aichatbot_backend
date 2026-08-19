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
    ProductCreate, ProductUpdate, ProductOut,
    OrderCreate, OrderStatusUpdate, OrderOut,
    EcommerceSettingsOut, EcommerceSettingsUpdate
)
from app.services.ecommerce.product_service import ProductService
from app.services.ecommerce.order_service import OrderService

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
    sms_cfg = settings.get("sms", {})

    app_key = bkash_cfg.get("app_key", "")
    masked_app_key = f"{app_key[:4]}...{app_key[-4:]}" if len(app_key) > 8 else ("Configured" if app_key else None)
    
    sender_id = sms_cfg.get("sender_id", "")
    masked_sender = sender_id if sender_id else None

    return {
        "business_category": tenant.business_category or "ecommerce",
        "cod_enabled": settings.get("cod_enabled", True),
        "bkash_enabled": bkash_cfg.get("enabled", False),
        "bkash_is_sandbox": bkash_cfg.get("is_sandbox", True),
        "bkash_base_url": bkash_cfg.get("base_url", "https://tokenized.sandbox.bka.sh/v1.2.0-beta"),
        "bkash_app_key_masked": masked_app_key,
        "bkash_username_masked": bkash_cfg.get("username"),
        "delivery_charge_inside_dhaka": settings.get("delivery_charge_inside_dhaka", 60.0),
        "delivery_charge_outside_dhaka": settings.get("delivery_charge_outside_dhaka", 120.0),
        "sms_notifications_enabled": sms_cfg.get("enabled", True),
        "sms_provider": sms_cfg.get("provider", "smsmatrix"),
        "sms_sender_id_masked": masked_sender,
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

    # bKash Settings
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
    settings["sms"] = sms_cfg
    tenant.ecommerce_settings = settings

    await db.commit()
    await db.refresh(tenant)

    app_key = bkash_cfg.get("app_key", "")
    masked_app_key = f"{app_key[:4]}...{app_key[-4:]}" if len(app_key) > 8 else ("Configured" if app_key else None)

    return {
        "business_category": tenant.business_category or "ecommerce",
        "cod_enabled": settings.get("cod_enabled", True),
        "bkash_enabled": bkash_cfg.get("enabled", False),
        "bkash_is_sandbox": bkash_cfg.get("is_sandbox", True),
        "bkash_base_url": bkash_cfg.get("base_url", "https://tokenized.sandbox.bka.sh/v1.2.0-beta"),
        "bkash_app_key_masked": masked_app_key,
        "bkash_username_masked": bkash_cfg.get("username"),
        "delivery_charge_inside_dhaka": settings.get("delivery_charge_inside_dhaka", 60.0),
        "delivery_charge_outside_dhaka": settings.get("delivery_charge_outside_dhaka", 120.0),
        "sms_notifications_enabled": sms_cfg.get("enabled", True),
        "sms_provider": sms_cfg.get("provider", "smsmatrix"),
        "sms_sender_id_masked": sms_cfg.get("sender_id"),
        "sms_order_template": settings.get("sms_order_template")
    }
