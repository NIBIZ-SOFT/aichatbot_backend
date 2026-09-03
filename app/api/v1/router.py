from fastapi import APIRouter
from app.api.v1 import (
    auth, tenants, conversations, operations, superadmin,
    analytics, payment, plans, ecommerce, widget_commerce, widget_payments,
    health, meta_data
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(tenants.router)
api_router.include_router(conversations.router)
api_router.include_router(widget_commerce.router)
api_router.include_router(widget_payments.router)
api_router.include_router(operations.router)
api_router.include_router(superadmin.router)
api_router.include_router(analytics.router)
api_router.include_router(payment.router)
api_router.include_router(plans.router)
api_router.include_router(ecommerce.router)
api_router.include_router(meta_data.router)


