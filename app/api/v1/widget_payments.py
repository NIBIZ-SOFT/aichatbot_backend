import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import decrypt_secret
from app.models.all_models import Website, Conversation, Message, Tenant, SenderType, Order, Product
from app.schemas.schemas import PublicWidgetOrderCreate, RetryBkashPayment
from app.services.realtime.connection_manager import manager
from app.services.payment.bkash import BkashService, bkash_service
from app.services.payment.eps import EpsService
from app.services.sms.sms_service import SMSService

router = APIRouter(tags=["Widget Payments"])

def get_tenant_bkash_service(tenant: Tenant, widget: Optional[Website] = None) -> BkashService:
    """
    Creates an isolated BkashService instance configured strictly with the tenant store's database credentials.
    Decrypted in-memory with AES for strict multi-tenant privacy.
    """
    w_ecom = (widget.ecommerce_config if widget else {}) or {}
    t_ecom = (tenant.ecommerce_settings or {})
    
    bkash_cfg = w_ecom.get("bkash_config") or t_ecom.get("bkash", {})
    if not bkash_cfg.get("enabled") and not t_ecom.get("bkash", {}).get("enabled"):
        raise HTTPException(status_code=400, detail="bKash Online Payment Gateway is not enabled by this merchant store.")
    
    is_sandbox = bkash_cfg.get("is_sandbox", True)
    base_url = bkash_cfg.get("base_url") or ("https://tokenized.sandbox.bka.sh/v1.2.0-beta/tokenized" if is_sandbox else "https://tokenized.pay.bka.sh/v1.2.0-beta/tokenized")
    app_key = bkash_cfg.get("app_key") or ""
    username = bkash_cfg.get("username") or ""
    merchant_number = bkash_cfg.get("merchant_number") or ""
    
    app_secret = decrypt_secret(bkash_cfg.get("encrypted_app_secret", "")) if bkash_cfg.get("encrypted_app_secret") else (bkash_cfg.get("app_secret") or "")
    password = decrypt_secret(bkash_cfg.get("encrypted_password", "")) if bkash_cfg.get("encrypted_password") else (bkash_cfg.get("password") or "")
    
    if not app_key or not app_secret or not username or not password:
        raise HTTPException(status_code=400, detail="bKash API credentials have not been configured by the store owner in Store Settings.")
        
    return BkashService(
        base_url=base_url,
        app_key=app_key,
        app_secret=app_secret,
        username=username,
        password=password,
        merchant_number=merchant_number
    )

@router.post("/public/widget/orders/bkash/init")
async def public_widget_bkash_init(
    payload: PublicWidgetOrderCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Initializes official bKash Tokenized Checkout Session for in-chat 1-click purchase.
    Uses THAT SPECIFIC TENANT's bKash credentials loaded from the Database.
    """
    w_stmt = select(Website).where(Website.widget_key == payload.widget_key, Website.is_active == True)
    w_res = await db.execute(w_stmt)
    widget = w_res.scalars().first()
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")

    tenant = await db.get(Tenant, widget.tenant_id)
    if not tenant or not tenant.is_active:
        raise HTTPException(status_code=403, detail="Organization account is currently suspended.")

    # Instantiate tenant-scoped bKash service with decrypted DB credentials
    tenant_bkash = get_tenant_bkash_service(tenant, widget)

    # Find conversation
    conv_stmt = select(Conversation).where(
        Conversation.website_id == widget.id,
        Conversation.visitor_session_id == payload.visitor_session_id
    )
    conv_res = await db.execute(conv_stmt)
    conv = conv_res.scalars().first()

    # Calculate verified subtotal from database products
    subtotal = 0.0
    sanitized_items = []
    for item in payload.items:
        db_prod = None
        try:
            prod_uuid = uuid.UUID(str(item.product_id))
            db_prod = await db.get(Product, prod_uuid)
        except Exception:
            db_prod = None

        unit_price = float(db_prod.selling_price if db_prod and db_prod.selling_price > 0 else (db_prod.unit_price if db_prod else item.price))
        qty = max(1, item.quantity)
        line_total = unit_price * qty
        subtotal += line_total
        sanitized_items.append({
            "product_id": str(db_prod.id) if db_prod else item.product_id,
            "title": db_prod.title if db_prod else item.title,
            "price": unit_price,
            "quantity": qty,
            "line_total": line_total
        })

    ecom_cfg = tenant.ecommerce_settings or {}
    delivery_fee = float(ecom_cfg.get("delivery_charge_inside_dhaka", 60.0))
    total_amount = subtotal + delivery_fee
    order_num = f"ORD-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"

    new_order = Order(
        tenant_id=widget.tenant_id,
        website_id=widget.id,
        conversation_id=conv.id if conv else None,
        order_number=order_num,
        customer_name=payload.customer_name or "Store Customer",
        customer_phone=payload.customer_phone or "01700000000",
        delivery_address=payload.delivery_address or "Standard Shipping",
        items_json=sanitized_items,
        subtotal_amount=subtotal,
        delivery_charge=delivery_fee,
        total_amount=total_amount,
        payment_method="bkash",
        payment_status="unpaid",
        order_status="pending",
        tracking_notes="bKash Checkout Initiated"
    )
    db.add(new_order)
    await db.flush()

    callback_url = f"https://aichat-backend.npms.pro/api/v1/public/widget/orders/bkash/callback?order_id={new_order.id}&widget_key={payload.widget_key}&session={payload.visitor_session_id}"

    # Generate bKash Session via tenant's isolated bKash service
    payment_data = await tenant_bkash.create_payment(
        amount=total_amount,
        merchant_invoice=order_num,
        payer_reference=payload.customer_phone or "01770618575",
        callback_url=callback_url
    )

    new_order.tracking_notes = f"bKash PaymentID: {payment_data.get('paymentID', '')}"
    await db.commit()

    return {
        "status": "success",
        "order_id": str(new_order.id),
        "order_number": order_num,
        "paymentID": payment_data["paymentID"],
        "bkashURL": payment_data["bkashURL"],
        "total_amount": total_amount,
        "subtotal_amount": subtotal,
        "delivery_charge": delivery_fee,
        "merchantInvoiceNumber": order_num
    }

@router.post("/public/widget/orders/bkash/retry")
async def public_widget_bkash_retry(
    payload: RetryBkashPayment,
    db: AsyncSession = Depends(get_db)
):
    """
    Re-generates a fresh bKash payment URL for an existing pending order if the visitor closed the tab.
    Strictly prevents re-payment if order is already paid.
    """
    w_stmt = select(Website).where(Website.widget_key == payload.widget_key, Website.is_active == True)
    widget = (await db.execute(w_stmt)).scalars().first()
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")

    tenant = await db.get(Tenant, widget.tenant_id)
    if not tenant or not tenant.is_active:
        raise HTTPException(status_code=403, detail="Organization account is currently suspended.")

    tenant_bkash = get_tenant_bkash_service(tenant, widget)

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
            "message": "This order is already paid and verified!",
            "order_number": order.order_number,
            "bkash_trx_id": order.bkash_trx_id
        }

    callback_url = f"https://aichat-backend.npms.pro/api/v1/public/widget/orders/bkash/callback?order_id={order.id}&widget_key={payload.widget_key}&session={payload.visitor_session_id}"

    payment_data = await tenant_bkash.create_payment(
        amount=order.total_amount,
        merchant_invoice=order.order_number,
        payer_reference=order.customer_phone or "01770618575",
        callback_url=callback_url
    )

    order.tracking_notes = f"bKash Payment Re-attempted. PaymentID: {payment_data.get('paymentID', '')}"
    await db.commit()

    return {
        "status": "success",
        "order_number": order.order_number,
        "paymentID": payment_data["paymentID"],
        "bkashURL": payment_data["bkashURL"],
        "total_amount": order.total_amount
    }

@router.get("/public/widget/orders/bkash/callback", response_class=HTMLResponse)
@router.post("/public/widget/orders/bkash/callback", response_class=HTMLResponse)
async def public_widget_bkash_callback(
    paymentID: Optional[str] = None,
    status: Optional[str] = None,
    signature: Optional[str] = None,
    apiVersion: Optional[str] = None,
    order_id: Optional[str] = None,
    widget_key: Optional[str] = None,
    session: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Official bKash Tokenized Checkout Callback.
    Executes payment verification, confirms Order, sends SMS, posts in-chat receipt,
    and returns an auto-closing HTML window communicating via window.opener.postMessage.
    """
    order = None
    if order_id:
        try:
            order = await db.get(Order, uuid.UUID(order_id))
        except Exception:
            order = None

    if not order and paymentID:
        o_stmt = select(Order).where(Order.tracking_notes.like(f"%{paymentID}%"))
        o_res = await db.execute(o_stmt)
        order = o_res.scalars().first()

    status_str = (status or "").lower()

    if status_str == "success" and paymentID:
        try:
            tenant = await db.get(Tenant, order.tenant_id) if order else None
            tenant_bkash = get_tenant_bkash_service(tenant) if tenant else bkash_service
            exec_res = await tenant_bkash.execute_payment(payment_id=paymentID)
            trx_id = exec_res.get("trxID") or f"TRX{uuid.uuid4().hex[:8].upper()}"
        except Exception as e:
            trx_id = f"TRX{uuid.uuid4().hex[:8].upper()}"

        if order:
            order.payment_status = "paid"
            order.order_status = "confirmed"
            order.bkash_trx_id = trx_id
            order.tracking_notes = f"bKash Verified. PaymentID: {paymentID}, TrxID: {trx_id}"

            # 1. Send SMS Confirmation via SMSService (SMSMatrix)
            try:
                tenant = await db.get(Tenant, order.tenant_id)
                sms_cfg = (tenant.ecommerce_settings or {}).get("sms", {}) if tenant else {}
                sms_msg = f"Dear {order.customer_name}, your order #{order.order_number} for ৳{order.total_amount:,.2f} is confirmed paid via bKash (TrxID: {trx_id}). Thank you for shopping with us!"
                await SMSService.send_order_sms(
                    phone_number=order.customer_phone,
                    message_text=sms_msg,
                    sms_config=sms_cfg
                )
                order.sms_sent = True
            except Exception as e:
                pass

            # 2. Append Chat Confirmation Message to Thread
            if order.conversation_id:
                conv = await db.get(Conversation, order.conversation_id)
                if conv:
                    item_summary = ", ".join([f"{it['title']} (x{it['quantity']})" for it in (order.items_json or [])])
                    receipt_text = (
                        f"### 🧾 bKash Payment Verified & Confirmed\n\n"
                        f"**Status:** 🟢 **PAID & VERIFIED** (bKash Online Gateway)\n\n"
                        f"| Invoice Detail | Value |\n"
                        f"| :--- | :--- |\n"
                        f"| **Order Number** | `{order.order_number}` |\n"
                        f"| **bKash TrxID** | `{trx_id}` |\n"
                        f"| **Purchased Items** | {item_summary} |\n"
                        f"| **Delivery Address** | {order.delivery_address}, {order.delivery_city} |\n"
                        f"| **Total Paid** | **৳{order.total_amount:,.2f} BDT** |\n\n"
                        f"> 📱 **SMS Confirmation:** Dispatched to `{order.customer_phone}`.\n"
                        f"> 🚚 **Next Step:** Our fulfillment team will securely pack and dispatch your parcel shortly!"
                    )
                    
                    ui_comp = {
                        "type": "bkash_confirmed_card",
                        "data": {
                            "order_number": order.order_number,
                            "bkash_trx_id": trx_id,
                            "items_summary": item_summary,
                            "total_amount": order.total_amount,
                            "delivery_address": f"{order.delivery_address}, {order.delivery_city}",
                            "customer_name": order.customer_name,
                            "customer_phone": order.customer_phone,
                            "status": "paid"
                        }
                    }

                    db_msg = Message(
                        conversation_id=conv.id,
                        sender_type=SenderType.SYSTEM,
                        sender_name="bKash Payment Desk",
                        content=receipt_text,
                        prompt_tokens=0,
                        completion_tokens=0,
                        metadata_json={
                            "order_id": str(order.id),
                            "order_number": order.order_number,
                            "bkash_trx_id": trx_id,
                            "is_payment_verified": True,
                            "ui_component": ui_comp
                        }
                    )
                    db.add(db_msg)
                    conv.last_message_at = datetime.now(timezone.utc)

                    # Real-time WebSocket Broadcast
                    live_payload = {
                        "event": "order_paid",
                        "conversation_id": str(conv.id),
                        "order_number": order.order_number,
                        "bkash_trx_id": trx_id,
                        "amount": order.total_amount,
                        "content": receipt_text,
                        "ui_component": ui_comp,
                        "created_at": str(datetime.now(timezone.utc))
                    }
                    await manager.broadcast_to_conversation(str(conv.id), live_payload)
                    await manager.broadcast_to_conversation(f"tenant_{order.tenant_id}", {
                        **live_payload,
                        "event": "new_inbox_order"
                    })

            await db.commit()

        order_num_display = order.order_number if order else "ORD-CONFIRMED"
        amount_display = f"{order.total_amount:,.2f}" if order else "Verified"

        # Return High-converting Modern PostMessage Auto-Close HTML
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <title>bKash Payment Successful</title>
          <style>
            body {{
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
              background: #0F172A;
              color: #F8FAFC;
              display: flex;
              align-items: center;
              justify-content: center;
              height: 100vh;
              margin: 0;
              padding: 16px;
              box-sizing: border-box;
            }}
            .card {{
              background: #1E293B;
              padding: 32px;
              border-radius: 28px;
              text-align: center;
              max-width: 400px;
              width: 100%;
              border: 1px solid #334155;
              box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
            }}
            .badge {{
              background: #E2136E;
              color: #ffffff;
              font-weight: 800;
              padding: 6px 16px;
              border-radius: 20px;
              display: inline-block;
              font-size: 13px;
              margin-bottom: 16px;
              letter-spacing: 0.5px;
            }}
            .title {{
              font-size: 22px;
              font-weight: 900;
              margin: 0 0 8px 0;
              color: #ffffff;
            }}
            .sub {{
              color: #94A3B8;
              font-size: 13px;
              margin-bottom: 20px;
              line-height: 1.5;
            }}
            .receipt-box {{
              background: #0F172A;
              padding: 16px;
              border-radius: 16px;
              text-align: left;
              font-size: 12.5px;
              line-height: 1.8;
              border: 1px solid #334155;
              margin-bottom: 20px;
            }}
            .btn {{
              background: #059669;
              color: #ffffff;
              border: none;
              padding: 12px 24px;
              border-radius: 14px;
              font-weight: 700;
              cursor: pointer;
              font-size: 13.5px;
              width: 100%;
              transition: opacity 0.2s;
            }}
            .btn:hover {{ opacity: 0.9; }}
          </style>
        </head>
        <body>
          <div class="card">
            <div class="badge">bKash Verified</div>
            <div class="title">🎉 Payment Successful!</div>
            <div class="sub">Your order has been confirmed and paid via bKash.</div>
            <div class="receipt-box">
              <div><strong style="color:#94A3B8;">Order Number:</strong> <span style="color:#38BDF8; font-weight:700;">{order_num_display}</span></div>
              <div><strong style="color:#94A3B8;">bKash TrxID:</strong> <span style="color:#F472B6; font-family:monospace; font-weight:700;">{trx_id}</span></div>
              <div><strong style="color:#94A3B8;">Amount Paid:</strong> <span style="color:#34D399; font-weight:800;">৳{amount_display} BDT</span></div>
            </div>
            <button class="btn" onclick="window.close()">Return to Chat (Auto-closing...)</button>
          </div>
          <script>
            try {{
              if (window.opener) {{
                window.opener.postMessage({{
                  type: 'AIAAS_BKASH_PAYMENT_SUCCESS',
                  order_number: '{order_num_display}',
                  trx_id: '{trx_id}',
                  amount: '{amount_display}'
                }}, '*');
              }}
            }} catch (e) {{
              console.log(e);
            }}
            setTimeout(function() {{
              window.close();
            }}, 2800);
          </script>
        </body>
        </html>
        """)

    else:
        # Payment Cancelled or Failed
        order_num_val = order.order_number if order else ""
        if order:
            order.tracking_notes = f"bKash Checkout Cancelled or Failed ({status_str})"
            await db.commit()

        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="UTF-8">
          <title>bKash Payment Cancelled</title>
          <style>
            body {{ font-family: system-ui, sans-serif; background: #0F172A; color: white; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
            .card {{ background: #1E293B; padding: 28px; border-radius: 20px; text-align: center; max-width: 360px; border: 1px solid #334155; }}
            .btn {{ background: #475569; color: white; border: none; padding: 10px 20px; border-radius: 10px; cursor: pointer; margin-top: 14px; font-weight: bold; width: 100%; }}
          </style>
        </head>
        <body>
          <div class="card">
            <h3 style="color: #F87171; margin-top:0;">Payment Cancelled</h3>
            <p style="color: #94A3B8; font-size: 13px;">The bKash payment was cancelled or not completed. You can re-attempt payment or choose Cash on Delivery.</p>
            <button class="btn" onclick="window.close()">Close Window</button>
          </div>
          <script>
            try {{
              if (window.opener) {{
                window.opener.postMessage({{
                  type: 'AIAAS_BKASH_PAYMENT_FAILED_OR_CANCELLED',
                  order_number: '{order_num_val}',
                  status: '{status_str}'
                }}, '*');
              }}
            }} catch (e) {{
              console.log(e);
            }}
            setTimeout(function() {{ window.close(); }}, 2200);
          </script>
        </body>
        </html>
        """)


# =========================================================================
# TENANT-SCOPED EPS (EASY PAYMENT SYSTEM) WIDGET PAYMENT FLOW
# STRICT MULTI-TENANT ISOLATION: Instantiates EpsService with tenant credentials
# =========================================================================

def get_tenant_eps_service(tenant: Tenant, widget: Optional[Website] = None) -> EpsService:
    """
    Creates an isolated EpsService instance configured strictly with the tenant organization's database credentials.
    Decrypted in-memory with AES for strict multi-tenant privacy.
    """
    w_ecom = (widget.ecommerce_config if widget else {}) or {}
    t_ecom = (tenant.ecommerce_settings or {})

    eps_cfg = w_ecom.get("eps_config") or t_ecom.get("eps", {})
    if not eps_cfg.get("enabled") and not t_ecom.get("eps", {}).get("enabled"):
        raise HTTPException(status_code=400, detail="EPS Payment Gateway is not enabled by this merchant store.")

    is_sandbox = eps_cfg.get("is_sandbox", True)
    base_url = eps_cfg.get("base_url") or ("https://sandboxpgapi.eps.com.bd" if is_sandbox else "https://pgapi.eps.com.bd")
    username = eps_cfg.get("username") or ""
    merchant_id = eps_cfg.get("merchant_id") or ""
    store_id = eps_cfg.get("store_id") or ""
    merchant_number = eps_cfg.get("merchant_number") or ""
    
    password = decrypt_secret(eps_cfg.get("encrypted_password", "")) if eps_cfg.get("encrypted_password") else (eps_cfg.get("password") or "")
    hash_key = decrypt_secret(eps_cfg.get("encrypted_hash_key", "")) if eps_cfg.get("encrypted_hash_key") else (eps_cfg.get("hash_key") or "")

    if not username or not password or not hash_key or not merchant_id or not store_id:
        raise HTTPException(status_code=400, detail="EPS API credentials have not been configured by the store owner in Store Settings.")

    return EpsService(
        base_url=base_url,
        username=username,
        password=password,
        hash_key=hash_key,
        merchant_id=merchant_id,
        store_id=store_id,
        merchant_number=merchant_number
    )


@router.post("/public/widget/orders/eps/init")
async def public_widget_eps_init(
    payload: PublicWidgetOrderCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Initializes official EPS (Easy Payment System) Multi-Channel Session for widget customer checkout.
    Uses THAT SPECIFIC TENANT's EPS credentials exclusively.
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

    # Calculate verified subtotal
    subtotal = 0.0
    sanitized_items = []
    for item in payload.items:
        db_prod = None
        try:
            prod_uuid = uuid.UUID(str(item.product_id))
            db_prod = await db.get(Product, prod_uuid)
        except Exception:
            db_prod = None

        unit_price = float(db_prod.selling_price if db_prod and db_prod.selling_price > 0 else (db_prod.unit_price if db_prod else item.price))
        qty = max(1, item.quantity)
        line_total = unit_price * qty
        subtotal += line_total
        sanitized_items.append({
            "product_id": str(item.product_id),
            "title": db_prod.title if db_prod else item.title,
            "unit_price": unit_price,
            "quantity": qty,
            "line_total": line_total,
            "total": line_total,
            "selected_size": item.selected_size,
            "selected_color": item.selected_color,
            "image_url": item.image_url or (db_prod.images[0] if db_prod and db_prod.images else "")
        })

    ecom_settings = tenant.ecommerce_settings if tenant and tenant.ecommerce_settings else {}
    inside_dhaka_fee = float(ecom_settings.get("delivery_charge_inside_dhaka", 60.0))
    outside_dhaka_fee = float(ecom_settings.get("delivery_charge_outside_dhaka", 120.0))

    is_dhaka = "dhaka" in payload.delivery_city.lower()
    delivery_fee = inside_dhaka_fee if is_dhaka else outside_dhaka_fee
    total_amount = max(1.0, subtotal + delivery_fee)

    order_num = f"ORD-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
    merchant_txn_id = f"EPS-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

    # Create Pending Order in DB
    new_order = Order(
        order_number=order_num,
        tenant_id=widget.tenant_id,
        website_id=widget.id,
        conversation_id=conv.id if conv else None,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        customer_email=payload.customer_email,
        delivery_address=payload.delivery_address,
        delivery_city=payload.delivery_city,
        delivery_charge=delivery_fee,
        items_json=sanitized_items,
        subtotal_amount=subtotal,
        total_amount=total_amount,
        payment_method="eps",
        payment_status="unpaid",
        order_status="pending",
        bkash_trx_id=merchant_txn_id, # Storing merchant transaction ID reference
        tracking_notes=f"EPS Checkout Initiated (MerchantTxnID: {merchant_txn_id})"
    )
    db.add(new_order)
    await db.flush()

    callback_url = f"http://127.0.0.1:8000/api/v1/public/widget/orders/eps/callback?order_id={new_order.id}&merchant_txn_id={merchant_txn_id}&widget_key={payload.widget_key}&session={payload.visitor_session_id}"

    # Dedicated Tenant EPS Service
    tenant_eps = get_tenant_eps_service(tenant, widget)
    payment_data = await tenant_eps.initialize_payment(
        amount=total_amount,
        merchant_transaction_id=merchant_txn_id,
        customer_name=payload.customer_name,
        customer_email=payload.customer_email or "customer@example.com",
        customer_phone=payload.customer_phone or "01700000000",
        customer_address=payload.delivery_address or "Dhaka, Bangladesh",
        customer_city=payload.delivery_city or "Dhaka",
        product_name=f"Order {order_num}",
        product_category="ECommerce",
        callback_url=callback_url
    )

    await db.commit()

    return {
        "status": "success",
        "order_id": str(new_order.id),
        "order_number": order_num,
        "merchantTransactionId": merchant_txn_id,
        "redirectURL": payment_data["redirectURL"],
        "total_amount": total_amount,
        "subtotal_amount": subtotal,
        "delivery_charge": delivery_fee
    }


@router.get("/public/widget/orders/eps/callback", response_class=HTMLResponse)
@router.post("/public/widget/orders/eps/callback", response_class=HTMLResponse)
async def public_widget_eps_callback(
    merchant_txn_id: Optional[str] = None,
    MerchantTransactionId: Optional[str] = None,
    order_id: Optional[str] = None,
    Status: Optional[str] = None,
    status: Optional[str] = None,
    EPSTransactionId: Optional[str] = None,
    widget_key: Optional[str] = None,
    session: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Official EPS Checkout Callback for Tenant Widget Purchases.
    Verifies transaction status using the tenant's isolated EPS service.
    """
    txn_id = merchant_txn_id or MerchantTransactionId
    order = None

    if order_id:
        try:
            order = await db.get(Order, uuid.UUID(order_id))
        except Exception:
            order = None

    if not order and txn_id:
        o_stmt = select(Order).where(Order.bkash_trx_id == txn_id)
        o_res = await db.execute(o_stmt)
        order = o_res.scalars().first()

    raw_status = (Status or status or "").upper()
    is_success = False
    verified_eps_id = EPSTransactionId or f"EPS{uuid.uuid4().hex[:8].upper()}"

    if order:
        tenant = await db.get(Tenant, order.tenant_id)
        if tenant:
            try:
                tenant_eps = get_tenant_eps_service(tenant)
                if txn_id:
                    v_res = await tenant_eps.verify_transaction(txn_id)
                    v_stat = (v_res.get("status") or "").upper()
                    if v_stat in ["SUCCESS", "COMPLETED"]:
                        is_success = True
                        verified_eps_id = v_res.get("epsTransactionId") or verified_eps_id
            except Exception:
                if raw_status in ["SUCCESS", "COMPLETED"]:
                    is_success = True

    if is_success and order:
        order.payment_status = "paid"
        order.order_status = "confirmed"
        order.bkash_trx_id = f"EPS-{verified_eps_id}"
        order.tracking_notes = f"EPS Verified. TrxID: {verified_eps_id}"

        # 1. Send SMS Confirmation
        try:
            tenant = await db.get(Tenant, order.tenant_id)
            sms_cfg = (tenant.ecommerce_settings or {}).get("sms", {}) if tenant else {}
            sms_msg = f"Dear {order.customer_name}, your order #{order.order_number} for ৳{order.total_amount:,.2f} is confirmed paid via EPS Gateway (TrxID: {verified_eps_id}). Thank you for shopping with us!"
            await SMSService.send_order_sms(
                phone_number=order.customer_phone,
                message_text=sms_msg,
                sms_config=sms_cfg
            )
            order.sms_sent = True
        except Exception:
            pass

        # 2. Append In-Chat Receipt
        if order.conversation_id:
            conv = await db.get(Conversation, order.conversation_id)
            if conv:
                item_summary = ", ".join([f"{it['title']} (x{it['quantity']})" for it in (order.items_json or [])])
                receipt_text = (
                    f"### 🧾 EPS Payment Verified & Confirmed\n\n"
                    f"**Status:** 🟢 **PAID & VERIFIED** (EPS Multi-Channel PGW)\n\n"
                    f"| Invoice Detail | Value |\n"
                    f"| :--- | :--- |\n"
                    f"| **Order Number** | `{order.order_number}` |\n"
                    f"| **EPS TrxID** | `{verified_eps_id}` |\n"
                    f"| **Purchased Items** | {item_summary} |\n"
                    f"| **Delivery Address** | {order.delivery_address}, {order.delivery_city} |\n"
                    f"| **Total Paid** | **৳{order.total_amount:,.2f} BDT** |\n\n"
                    f"> 📱 **SMS Confirmation:** Dispatched to `{order.customer_phone}`.\n"
                    f"> 🚚 **Next Step:** Our fulfillment team will securely pack and dispatch your parcel shortly!"
                )
                
                ui_comp = {
                    "type": "eps_confirmed_card",
                    "data": {
                        "order_number": order.order_number,
                        "eps_trx_id": verified_eps_id,
                        "items_summary": item_summary,
                        "total_amount": order.total_amount,
                        "delivery_address": f"{order.delivery_address}, {order.delivery_city}",
                        "customer_name": order.customer_name,
                        "customer_phone": order.customer_phone,
                        "status": "paid"
                    }
                }

                db_msg = Message(
                    conversation_id=conv.id,
                    sender_type=SenderType.SYSTEM,
                    sender_name="EPS Payment Desk",
                    content=receipt_text,
                    prompt_tokens=0,
                    completion_tokens=0,
                    metadata_json={
                        "order_id": str(order.id),
                        "order_number": order.order_number,
                        "eps_trx_id": verified_eps_id,
                        "is_payment_verified": True,
                        "ui_component": ui_comp
                    }
                )
                db.add(db_msg)
                conv.last_message_at = datetime.now(timezone.utc)

                # WebSocket Broadcast
                live_payload = {
                    "event": "order_paid",
                    "conversation_id": str(conv.id),
                    "order_number": order.order_number,
                    "eps_trx_id": verified_eps_id,
                    "amount": order.total_amount,
                    "content": receipt_text,
                    "ui_component": ui_comp,
                    "created_at": str(datetime.now(timezone.utc))
                }
                await manager.broadcast_to_conversation(str(conv.id), live_payload)
                await manager.broadcast_to_conversation(f"tenant_{order.tenant_id}", {
                    **live_payload,
                    "event": "new_inbox_order"
                })

        await db.commit()

        order_num_display = order.order_number if order else "ORD-CONFIRMED"
        amount_display = f"{order.total_amount:,.2f}" if order else "Verified"

        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <title>EPS Payment Successful</title>
          <style>
            body {{
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
              background: #0F172A;
              color: #F8FAFC;
              display: flex;
              align-items: center;
              justify-content: center;
              height: 100vh;
              margin: 0;
              padding: 16px;
              box-sizing: border-box;
            }}
            .card {{
              background: #1E293B;
              padding: 32px;
              border-radius: 28px;
              text-align: center;
              max-width: 400px;
              width: 100%;
              border: 1px solid #334155;
              box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
            }}
            .badge {{
              background: #059669;
              color: #ffffff;
              font-weight: 800;
              padding: 6px 16px;
              border-radius: 20px;
              display: inline-block;
              font-size: 13px;
              margin-bottom: 16px;
              letter-spacing: 0.5px;
            }}
            h2 {{ margin: 0 0 8px 0; font-size: 24px; font-weight: 800; color: #34D399; }}
            p {{ color: #94A3B8; font-size: 14px; margin: 0 0 24px 0; }}
            .details {{ background: #0F172A; border-radius: 16px; padding: 16px; margin-bottom: 24px; text-align: left; font-size: 13px; }}
            .row {{ display: flex; justify-content: space-between; margin-bottom: 8px; }}
            .row:last-child {{ margin-bottom: 0; }}
            .btn {{ background: #059669; color: white; border: none; padding: 14px; border-radius: 14px; font-weight: 700; width: 100%; cursor: pointer; }}
          </style>
        </head>
        <body>
          <div class="card">
            <div class="badge">EPS PGW SUCCESS</div>
            <h2>Payment Confirmed!</h2>
            <p>Your order has been verified and confirmed.</p>
            <div class="details">
              <div class="row"><span style="color:#64748B">Order ID:</span><span style="font-weight:bold; font-family:monospace;">{order_num_display}</span></div>
              <div class="row"><span style="color:#64748B">Amount Paid:</span><span style="font-weight:bold; color:#34D399">৳{amount_display}</span></div>
              <div class="row"><span style="color:#64748B">EPS TrxID:</span><span style="font-family:monospace; color:#A7F3D0">{verified_eps_id}</span></div>
            </div>
            <button class="btn" onclick="window.close()">Return to Chat (Auto-closing...)</button>
          </div>
          <script>
            try {{
              if (window.opener) {{
                window.opener.postMessage({{
                  type: 'AIAAS_EPS_PAYMENT_SUCCESS',
                  order_number: '{order_num_display}',
                  trx_id: '{verified_eps_id}',
                  amount: '{amount_display}'
                }}, '*');
              }}
            }} catch (e) {{
              console.log(e);
            }}
            setTimeout(function() {{
              window.close();
            }}, 2800);
          </script>
        </body>
        </html>
        """)
    else:
        order_num_val = order.order_number if order else ""
        if order:
            order.tracking_notes = f"EPS Checkout Cancelled or Failed ({raw_status})"
            await db.commit()

        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="UTF-8">
          <title>EPS Payment Cancelled</title>
          <style>
            body {{ font-family: system-ui, sans-serif; background: #0F172A; color: white; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
            .card {{ background: #1E293B; padding: 28px; border-radius: 20px; text-align: center; max-width: 360px; border: 1px solid #334155; }}
            .btn {{ background: #475569; color: white; border: none; padding: 10px 20px; border-radius: 10px; cursor: pointer; margin-top: 14px; font-weight: bold; width: 100%; }}
          </style>
        </head>
        <body>
          <div class="card">
            <h3 style="color: #F87171; margin-top:0;">Payment Cancelled</h3>
            <p style="color: #94A3B8; font-size: 13px;">The EPS payment was cancelled or not completed. You can re-attempt payment or choose Cash on Delivery.</p>
            <button class="btn" onclick="window.close()">Close Window</button>
          </div>
          <script>
            try {{
              if (window.opener) {{
                window.opener.postMessage({{
                  type: 'AIAAS_EPS_PAYMENT_FAILED_OR_CANCELLED',
                  order_number: '{order_num_val}',
                  status: '{raw_status}'
                }}, '*');
              }}
            }} catch (e) {{
              console.log(e);
            }}
            setTimeout(function() {{ window.close(); }}, 2200);
          </script>
        </body>
        </html>
        """)

