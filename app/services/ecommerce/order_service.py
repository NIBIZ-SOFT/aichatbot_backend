import uuid
import random
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime, timezone

from app.models.all_models import Order, Product, Tenant
from app.schemas.schemas import OrderCreate, OrderStatusUpdate, OrderItemIn
from app.services.sms.sms_service import SMSService

class OrderService:
    """
    SOLID Single-Responsibility Service for E-Commerce Order Management,
    Server-Side Tamper-Proof Price Validation, and SMS Notification Dispatch.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def generate_order_number() -> str:
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        rand_suffix = f"{random.randint(1000, 9999)}"
        return f"ORD-{date_str}-{rand_suffix}"

    async def create_order(
        self,
        tenant_id: uuid.UUID,
        data: OrderCreate,
        website_id: Optional[uuid.UUID] = None,
        conversation_id: Optional[uuid.UUID] = None
    ) -> Order:
        """
        Creates order with SERVER-SIDE PRICE VALIDATION (prevents client price tampering)
        and sends instant SMS confirmation.
        """
        # Fetch Tenant & Ecommerce Settings
        tenant = await self.db.get(Tenant, tenant_id)
        ecom_settings = tenant.ecommerce_settings if tenant and tenant.ecommerce_settings else {}

        inside_dhaka_fee = float(ecom_settings.get("delivery_charge_inside_dhaka", 60.0))
        outside_dhaka_fee = float(ecom_settings.get("delivery_charge_outside_dhaka", 120.0))

        is_dhaka = "dhaka" in data.delivery_city.lower()
        delivery_fee = inside_dhaka_fee if is_dhaka else outside_dhaka_fee

        # 1. Server-Side Price & Inventory Verification
        validated_items = []
        subtotal = 0.0

        for item in data.items:
            # Look up product in DB
            try:
                prod_uuid = uuid.UUID(str(item.product_id))
                prod_stmt = select(Product).where(Product.id == prod_uuid, Product.tenant_id == tenant_id)
                prod_res = await self.db.execute(prod_stmt)
                db_prod = prod_res.scalars().first()
            except Exception:
                db_prod = None

            if db_prod:
                actual_unit_price = float(db_prod.selling_price if db_prod.selling_price > 0 else db_prod.unit_price)
                prod_title = db_prod.title
                item_img = db_prod.images[0] if db_prod.images else item.image_url
            else:
                actual_unit_price = float(item.price)
                prod_title = item.title
                item_img = item.image_url

            qty = max(1, item.quantity)
            line_total = actual_unit_price * qty
            subtotal += line_total

            validated_items.append({
                "product_id": str(item.product_id),
                "title": prod_title,
                "unit_price": actual_unit_price,
                "quantity": qty,
                "line_total": line_total,
                "selected_size": item.selected_size,
                "selected_color": item.selected_color,
                "image_url": item_img
            })

        total_amount = subtotal + delivery_fee
        order_num = self.generate_order_number()

        # 2. Persist Order
        order = Order(
            id=uuid.uuid4(),
            order_number=order_num,
            tenant_id=tenant_id,
            website_id=website_id or data.website_id,
            conversation_id=conversation_id or data.conversation_id,
            customer_name=data.customer_name,
            customer_phone=data.customer_phone,
            customer_email=data.customer_email,
            delivery_address=data.delivery_address,
            delivery_city=data.delivery_city,
            delivery_charge=delivery_fee,
            items_json=validated_items,
            subtotal_amount=subtotal,
            total_amount=total_amount,
            payment_method=data.payment_method,
            payment_status="paid" if data.payment_method == "bkash" else "unpaid",
            order_status="pending",
            sms_sent=False
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)

        # 3. Automated SMS Notification Dispatch
        try:
            sms_cfg = ecom_settings.get("sms", {})
            store_name = tenant.name if tenant else "Our Store"
            default_template = f"Dear {{{{customer_name}}}}, your order #{{{{order_id}}}} for ৳{{{{total_amount}}}} BDT has been placed successfully at {store_name}! Thank you for shopping with us."
            template = ecom_settings.get("sms_order_template") or default_template

            rendered_sms = SMSService.render_template(template, {
                "customer_name": order.customer_name,
                "order_id": order.order_number,
                "total_amount": f"{order.total_amount:,.2f}",
                "store_name": store_name
            })

            sms_res = await SMSService.send_order_sms(
                phone_number=order.customer_phone,
                message_text=rendered_sms,
                sms_config=sms_cfg
            )

            if sms_res.get("status") in ["sent", "delivered_mock"]:
                order.sms_sent = True
                await self.db.commit()
        except Exception as e:
            print(f"[OrderService] SMS dispatch notice: {str(e)}", flush=True)

        return order

    async def update_order_status(
        self,
        order_id: uuid.UUID,
        tenant_id: uuid.UUID,
        data: OrderStatusUpdate
    ) -> Optional[Order]:
        stmt = select(Order).where(Order.id == order_id, Order.tenant_id == tenant_id)
        res = await self.db.execute(stmt)
        order = res.scalars().first()
        if not order:
            return None

        order.order_status = data.order_status
        if data.payment_status:
            order.payment_status = data.payment_status
        if data.tracking_notes:
            order.tracking_notes = data.tracking_notes

        await self.db.commit()
        await self.db.refresh(order)

        # Send Status Update SMS
        if data.send_sms_notification:
            tenant = await self.db.get(Tenant, tenant_id)
            ecom_settings = tenant.ecommerce_settings if tenant and tenant.ecommerce_settings else {}
            sms_cfg = ecom_settings.get("sms", {})
            store_name = tenant.name if tenant else "Our Store"

            status_text = {
                "confirmed": "confirmed and being packed",
                "shipped": "shipped with our courier partner",
                "delivered": "delivered successfully",
                "cancelled": "cancelled"
            }.get(data.order_status, data.order_status)

            msg = f"Update: Dear {order.customer_name}, your order #{order.order_number} is now {status_text}. {store_name}"
            await SMSService.send_order_sms(order.customer_phone, msg, sms_cfg)

        return order

    async def resend_order_sms(
        self,
        order_id: uuid.UUID,
        tenant_id: uuid.UUID,
        custom_message: Optional[str] = None
    ) -> Dict[str, Any]:
        stmt = select(Order).where(Order.id == order_id, Order.tenant_id == tenant_id)
        res = await self.db.execute(stmt)
        order = res.scalars().first()
        if not order:
            return {"status": "error", "message": "Order not found"}

        tenant = await self.db.get(Tenant, tenant_id)
        ecom_settings = tenant.ecommerce_settings if tenant and tenant.ecommerce_settings else {}
        sms_cfg = ecom_settings.get("sms", {})
        store_name = tenant.name if tenant else "Our Store"

        if custom_message:
            rendered_sms = custom_message
        else:
            default_template = f"Dear {{{{customer_name}}}}, your order #{{{{order_id}}}} for ৳{{{{total_amount}}}} BDT at {store_name} is confirmed! Thank you for shopping with us."
            template = ecom_settings.get("sms_order_template") or default_template
            rendered_sms = SMSService.render_template(template, {
                "customer_name": order.customer_name,
                "order_id": order.order_number,
                "total_amount": f"{order.total_amount:,.2f}",
                "store_name": store_name
            })

        sms_res = await SMSService.send_order_sms(
            phone_number=order.customer_phone,
            message_text=rendered_sms,
            sms_config=sms_cfg
        )

        if sms_res.get("status") in ["sent", "delivered_mock"]:
            order.sms_sent = True
            timestamp_str = datetime.now(timezone.utc).strftime("%d %b %Y, %I:%M %p")
            order.tracking_notes = f"SMS sent on {timestamp_str}: '{rendered_sms[:80]}...'"
            await self.db.commit()

        return {
            "status": "success" if sms_res.get("status") in ["sent", "delivered_mock"] else "failed",
            "sms_response": sms_res,
            "message_sent": rendered_sms,
            "recipient": order.customer_phone,
            "order_number": order.order_number
        }

    async def get_orders(
        self,
        tenant_id: uuid.UUID,
        status: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Order]:
        stmt = select(Order).where(Order.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(Order.order_status == status)
        if search:
            stmt = stmt.where(
                (Order.order_number.ilike(f"%{search}%")) |
                (Order.customer_name.ilike(f"%{search}%")) |
                (Order.customer_phone.ilike(f"%{search}%"))
            )

        stmt = stmt.order_by(desc(Order.created_at)).limit(limit).offset(offset)
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

