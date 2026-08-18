import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.all_models import User, UserRole
from app.schemas.analytics import (
    AnalyticsOverviewResponse, CSATSubmitPayload
)
from app.services.analytics.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["Analytics & CSAT"])

@router.get("/overview", response_model=AnalyticsOverviewResponse)
async def get_analytics_overview(
    time_range: str = Query("7d", regex="^(7d|30d|90d)$", description="Filter analytics by 7d, 30d, or 90d"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns complete real-time CSAT, AI resolution rates, response latency, and agent performance.
    Strictly isolated to current tenant.
    """
    if not user.tenant_id and user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=400, detail="Tenant context required")

    # If Super Admin visits, pick the primary active tenant or raise
    target_tenant_id = user.tenant_id
    if not target_tenant_id:
        from sqlalchemy import select
        from app.models.all_models import Tenant
        res = await db.execute(select(Tenant.id).limit(1))
        target_tenant_id = res.scalars().first()
        if not target_tenant_id:
            raise HTTPException(status_code=404, detail="No active tenant found")

    analytics_svc = AnalyticsService(db=db)
    return await analytics_svc.get_tenant_overview(tenant_id=target_tenant_id, time_range=time_range)

@router.post("/conversations/{conversation_id}/csat")
async def submit_conversation_csat(
    conversation_id: uuid.UUID,
    payload: CSATSubmitPayload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Submits 1-5 star CSAT customer rating and feedback text for a conversation.
    """
    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    analytics_svc = AnalyticsService(db=db)
    success = await analytics_svc.submit_csat_rating(
        tenant_id=user.tenant_id,
        conversation_id=conversation_id,
        rating=payload.rating,
        feedback=payload.feedback
    )
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found in your tenant workspace")

    return {"status": "success", "message": f"Recorded {payload.rating}-star CSAT rating successfully"}
