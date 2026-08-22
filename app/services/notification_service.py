import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.all_models import Notification

async def create_notification(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    title: str,
    message: str,
    type: str = "info",
    link: Optional[str] = None
) -> Notification:
    """
    Central helper to create an in-app notification in PostgreSQL.
    Types: 'order', 'handover', 'billing', 'knowledge', 'system', 'csat', 'lead'
    """
    notif = Notification(
        tenant_id=tenant_id,
        title=title,
        message=message,
        type=type,
        is_read=False,
        link=link
    )
    db.add(notif)
    await db.commit()
    await db.refresh(notif)
    return notif

async def notify_new_order(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    order_number: str,
    customer_name: str,
    total_amount_bdt: float,
    payment_method: str = "cod"
):
    title = f"🛒 New Order #{order_number}"
    method_label = "Cash on Delivery" if payment_method == "cod" else "bKash Online"
    msg = f"New order for ৳{total_amount_bdt:,.2f} placed by {customer_name} via {method_label}."
    return await create_notification(
        db,
        tenant_id=tenant_id,
        title=title,
        message=msg,
        type="order",
        link="/orders"
    )

async def notify_handover_requested(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    conversation_id: str,
    customer_identifier: str,
    reason: Optional[str] = None
):
    title = "🚨 Live Human Agent Requested"
    msg = f"Customer '{customer_identifier}' requested human assistance in support queue."
    if reason:
        msg += f" Reason: {reason}"
    return await create_notification(
        db,
        tenant_id=tenant_id,
        title=title,
        message=msg,
        type="handover",
        link="/inbox"
    )

async def notify_payment_received(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    amount_bdt: float,
    trx_id: str,
    plan_name: str
):
    title = "💳 Payment Received & Subscription Active"
    msg = f"bKash transaction #{trx_id} for ৳{amount_bdt:,.2f} verified. Plan: {plan_name}."
    return await create_notification(
        db,
        tenant_id=tenant_id,
        title=title,
        message=msg,
        type="billing",
        link="/subscription"
    )

async def notify_low_tokens(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    remaining_tokens: int,
    percent_used: int
):
    title = "⚡ Token Quota Alert"
    msg = f"You have consumed {percent_used}% of your monthly AI token quota ({remaining_tokens:,} tokens remaining)."
    return await create_notification(
        db,
        tenant_id=tenant_id,
        title=title,
        message=msg,
        type="billing",
        link="/subscription"
    )

async def notify_knowledge_ready(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    document_title: str,
    chunk_count: int
):
    title = "🧠 RAG Knowledge Base Indexed"
    msg = f"'{document_title}' has been successfully parsed and indexed into {chunk_count} neural vector embeddings."
    return await create_notification(
        db,
        tenant_id=tenant_id,
        title=title,
        message=msg,
        type="knowledge",
        link="/knowledge"
    )
