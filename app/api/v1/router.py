from fastapi import APIRouter
from app.api.v1 import auth, tenants, conversations, operations, superadmin, analytics, payment, plans

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(tenants.router)
api_router.include_router(conversations.router)
api_router.include_router(operations.router)
api_router.include_router(superadmin.router)
api_router.include_router(analytics.router)
api_router.include_router(payment.router)
api_router.include_router(plans.router)
