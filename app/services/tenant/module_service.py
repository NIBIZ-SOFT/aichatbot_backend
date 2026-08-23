import uuid
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.all_models import Tenant

# 10 Standard SaaS Module Definitions with Metadata
ALL_AVAILABLE_MODULES: Dict[str, Dict[str, Any]] = {
    "dashboard": {
        "id": "dashboard",
        "name": "Operations Dashboard",
        "description": "Live visitor metrics, recent inquiries overview, and system status.",
        "category": "OPERATIONS",
        "default_starter": True,
        "default_pro": True,
        "default_enterprise": True
    },
    "inbox": {
        "id": "inbox",
        "name": "Live Support Inbox",
        "description": "Live visitor chat queue, order tracking tickets, and agent takeover.",
        "category": "OPERATIONS",
        "default_starter": True,
        "default_pro": True,
        "default_enterprise": True
    },
    "contacts": {
        "id": "contacts",
        "name": "CRM Contacts & Buyers",
        "description": "Bangladeshi shopper profiles, lifetime spend, order history, and VIP tags.",
        "category": "OPERATIONS",
        "default_starter": False,
        "default_pro": True,
        "default_enterprise": True
    },
    "knowledge": {
        "id": "knowledge",
        "name": "AI Brain & Knowledge RAG",
        "description": "Train product catalogs, delivery guidelines, and live AI Simulator playground.",
        "category": "AI & KNOWLEDGE",
        "default_starter": True,
        "default_pro": True,
        "default_enterprise": True
    },
    "websites": {
        "id": "websites",
        "name": "Websites & Widget Studio",
        "description": "Connected storefronts and embeddable live chat widget script generator.",
        "category": "AI & KNOWLEDGE",
        "default_starter": False,
        "default_pro": True,
        "default_enterprise": True
    },
    "analytics": {
        "id": "analytics",
        "name": "Analytics & CSAT Engine",
        "description": "5-star customer ratings, AI autonomous resolution rate, and staff leaderboard.",
        "category": "METRICS & BILLING",
        "default_starter": False,
        "default_pro": True,
        "default_enterprise": True
    },
    "usage": {
        "id": "usage",
        "name": "AI Token Usage & Cost Meter",
        "description": "Official OpenAI tokenizer calculation with BDT (৳) conversion and daily history.",
        "category": "METRICS & BILLING",
        "default_starter": True,
        "default_pro": True,
        "default_enterprise": True
    },
    "subscription": {
        "id": "subscription",
        "name": "Subscription & Billing",
        "description": "Plan management, monthly billing invoices, and BDT upgrade checkout.",
        "category": "METRICS & BILLING",
        "default_starter": True,
        "default_pro": True,
        "default_enterprise": True
    },
    "team": {
        "id": "team",
        "name": "Team & Permissions (RBAC)",
        "description": "Invite and manage up to 4 organization staff with role-based access control.",
        "category": "MANAGEMENT",
        "default_starter": False,
        "default_pro": True,
        "default_enterprise": True
    },
    "settings": {
        "id": "settings",
        "name": "Organization Settings",
        "description": "Company profile, logo, business hours, and operational contact info.",
        "category": "MANAGEMENT",
        "default_starter": True,
        "default_pro": True,
        "default_enterprise": True
    },
    "products": {
        "id": "products",
        "name": "Product Catalog & Inventory",
        "description": "Manage products, prices, images, and CDN widget priority rankings.",
        "category": "COMMERCE",
        "default_starter": True,
        "default_pro": True,
        "default_enterprise": True
    },
    "orders": {
        "id": "orders",
        "name": "Orders & Courier Dispatch",
        "description": "Track online orders, verify bKash payments, and dispatch with SMS alerts.",
        "category": "COMMERCE",
        "default_starter": True,
        "default_pro": True,
        "default_enterprise": True
    }
}

DEFAULT_FULL_MODULES: Dict[str, bool] = {
    mod_id: True for mod_id in ALL_AVAILABLE_MODULES.keys()
}

class TenantModuleService:
    """
    Decoupled Tenant Feature Flags & Module Access Service.
    Follows Single Responsibility Principle (SRP) & Open/Closed Principle (OCP).
    """

    @staticmethod
    def resolve_tenant_modules(tenant: Optional[Tenant]) -> Dict[str, bool]:
        """
        Returns full boolean map for all modules for a tenant.
        Adapts default commerce module visibility based on tenant business_category.
        """
        if not tenant:
            return DEFAULT_FULL_MODULES.copy()

        category = (tenant.business_category or "ecommerce").lower()
        is_ecom = (category == "ecommerce")

        stored = tenant.enabled_modules or {}
        resolved = {}
        for mod_id in ALL_AVAILABLE_MODULES.keys():
            if mod_id in ["products", "orders"]:
                resolved[mod_id] = stored.get(mod_id, is_ecom)
            else:
                resolved[mod_id] = stored.get(mod_id, True)

        return resolved

    @staticmethod
    async def update_tenant_modules(
        db: AsyncSession,
        tenant_id: uuid.UUID,
        new_module_flags: Dict[str, bool]
    ) -> Optional[Dict[str, bool]]:
        """
        Persists updated module flags for a tenant into PostgreSQL.
        """
        stmt = select(Tenant).where(Tenant.id == tenant_id)
        res = await db.execute(stmt)
        tenant = res.scalars().first()
        if not tenant:
            return None

        from sqlalchemy.orm.attributes import flag_modified
        current = dict(tenant.enabled_modules or {})
        # Merge safely
        for k, v in new_module_flags.items():
            if k in ALL_AVAILABLE_MODULES:
                current[k] = bool(v)

        tenant.enabled_modules = current
        flag_modified(tenant, "enabled_modules")
        await db.commit()
        await db.refresh(tenant)

        return TenantModuleService.resolve_tenant_modules(tenant)
