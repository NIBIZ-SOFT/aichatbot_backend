import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.all_models import Website, Conversation, Message, Tenant, SenderType, Order
from app.schemas.schemas import PublicWidgetOrderCreate, OrderCreate, OrderOut, SwitchOrderCOD
from app.services.realtime.connection_manager import manager
from app.services.ecommerce.product_service import ProductService
from app.services.ecommerce.order_service import OrderService
from app.services.sms.sms_service import SMSService

router = APIRouter(tags=["Widget E-Commerce"])

@router.get("/public/widget/products")
async def get_public_widget_products(
    widget_key: str,
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 10,
    db: AsyncSession = Depends(get_db)
):
    """
    Public endpoint for embeddable widget to fetch active product cards
    for in-chat product carousels and instant purchase.
    """
    w_stmt = select(Website).where(Website.widget_key == widget_key, Website.is_active == True)
    w_res = await db.execute(w_stmt)
    widget = w_res.scalars().first()
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found or inactive")

    # Check Tenant Suspension Status
    tenant = await db.get(Tenant, widget.tenant_id)
    if not tenant or not tenant.is_active:
        raise HTTPException(status_code=403, detail="Organization account is currently suspended.")

    service = ProductService(db)
    products = await service.get_products(
        tenant_id=widget.tenant_id,
        category=category,
        search=search,
        is_active=True,
        sort_by="priority",
        sort_dir="asc",
        limit=limit
    )

    return [
        {
            "id": str(p.id),
            "title": p.title,
            "category": p.category,
            "sku": p.sku,
            "unit_price": p.unit_price,
            "selling_price": p.selling_price,
            "stock_status": p.stock_status,
            "stock_quantity": p.stock_quantity,
            "images": p.images,
            "description": p.description,
            "specifications": p.specifications,
            "priority": p.priority
        }
        for p in products
    ]

@router.post("/public/widget/orders/checkout", response_model=OrderOut)
async def public_widget_order_checkout(
    payload: PublicWidgetOrderCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Instant in-chat 1-click checkout from the embeddable CDN widget.
    Performs SERVER-SIDE PRICE VALIDATION (anti-tampering), records order in /orders,
    creates a message in the chat thread, sends SMS confirmation, and broadcasts live alert.
    """
    w_stmt = select(Website).where(Website.widget_key == payload.widget_key, Website.is_active == True)
    w_res = await db.execute(w_stmt)
    widget = w_res.scalars().first()
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")

    tenant = await db.get(Tenant, widget.tenant_id)
    if not tenant or not tenant.is_active:
        raise HTTPException(status_code=403, detail="Organization account is currently suspended.")

    # Find conversation
    conv_stmt = select(Conversation).where(
        Conversation.website_id == widget.id,
        Conversation.visitor_session_id == payload.visitor_session_id
    )
    conv_res = await db.execute(conv_stmt)
    conv = conv_res.scalars().first()

    # Create Order via OrderService with server-side pricing
    order_svc = OrderService(db)
    order_create_data = OrderCreate(
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        customer_email=payload.customer_email,
        delivery_address=payload.delivery_address,
        delivery_city=payload.delivery_city,
        items=payload.items,
        payment_method=payload.payment_method,
        website_id=widget.id,
        conversation_id=conv.id if conv else None
    )

    order = await order_svc.create_order(
        tenant_id=widget.tenant_id,
        data=order_create_data,
        website_id=widget.id,
        conversation_id=conv.id if conv else None
    )

    # If conversation exists, post automated confirmation message to the chat thread
    if conv:
        item_summary = ", ".join([f"{it['title']} (x{it['quantity']})" for it in order.items_json])
        pmt_text = "Cash on Delivery" if order.payment_method == "cash_on_delivery" else "bKash Online Payment"
        
        chat_msg_text = (
            f"🎉 **Order Placed Successfully!**\n\n"
            f"• **Order Number:** `{order.order_number}`\n"
            f"• **Customer:** {order.customer_name} ({order.customer_phone})\n"
            f"• **Items:** {item_summary}\n"
            f"• **Delivery Address:** {order.delivery_address}, {order.delivery_city}\n"
            f"• **Payment Method:** {pmt_text}\n"
            f"• **Total Payable:** ৳{order.total_amount:,.2f} BDT (Including Delivery ৳{order.delivery_charge:,.2f})\n\n"
            f"An SMS confirmation has been sent to your phone. Our team will contact you shortly for dispatch!"
        )

        ai_msg = Message(
            conversation_id=conv.id,
            sender_type=SenderType.SYSTEM,
            sender_name="Padma Mart Order Desk",
            content=chat_msg_text,
            prompt_tokens=0,
            completion_tokens=0,
            metadata_json={"order_id": str(order.id), "order_number": order.order_number, "is_order_event": True}
        )
        db.add(ai_msg)
        conv.last_message_at = datetime.now(timezone.utc)
        await db.commit()

        # Broadcast order event to live visitor and tenant staff inbox
        order_event_payload = {
            "event": "order_placed",
            "conversation_id": str(conv.id),
            "order_number": order.order_number,
            "customer_name": order.customer_name,
            "total_amount": order.total_amount,
            "payment_method": order.payment_method,
            "content": chat_msg_text,
            "created_at": str(datetime.now(timezone.utc))
        }
        await manager.broadcast_to_conversation(str(conv.id), order_event_payload)
        await manager.broadcast_to_conversation(f"tenant_{widget.tenant_id}", {
            **order_event_payload,
            "event": "new_inbox_order"
        })

    return order

@router.post("/public/widget/orders/switch-cod")
async def public_widget_switch_cod(
    payload: SwitchOrderCOD,
    db: AsyncSession = Depends(get_db)
):
    """
    Converts a pending bKash order to Cash on Delivery (COD) in 1-click if the customer prefers COD.
    """
    w_stmt = select(Website).where(Website.widget_key == payload.widget_key, Website.is_active == True)
    widget = (await db.execute(w_stmt)).scalars().first()
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")

    o_stmt = select(Order).where(
        Order.order_number == payload.order_number,
        Order.tenant_id == widget.tenant_id
    )
    order = (await db.execute(o_stmt)).scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.payment_status == "paid":
        return {
            "status": "already_paid",
            "message": "This order is already paid via bKash.",
            "order_number": order.order_number
        }

    order.payment_method = "cash_on_delivery"
    order.payment_status = "unpaid"
    order.order_status = "confirmed"
    order.tracking_notes = "Customer switched payment method from bKash to Cash on Delivery."

    # Dispatch SMS
    try:
        tenant = await db.get(Tenant, order.tenant_id)
        sms_cfg = (tenant.ecommerce_settings or {}).get("sms", {}) if tenant else {}
        sms_msg = f"Dear {order.customer_name}, your order #{order.order_number} for ৳{order.total_amount:,.2f} is confirmed (Cash on Delivery). Thank you!"
        await SMSService.send_order_sms(
            phone_number=order.customer_phone,
            message_text=sms_msg,
            sms_config=sms_cfg
        )
        order.sms_sent = True
    except Exception as e:
        pass

    await db.commit()

    return {
        "status": "success",
        "order_number": order.order_number,
        "total_amount": order.total_amount,
        "payment_method": "cash_on_delivery",
        "message": "Order successfully switched to Cash on Delivery!"
    }
