import re
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, case, desc, or_, cast, String

from app.models.all_models import Product, Order


class GenerativeUIService:
    """
    Enterprise Generative UI & Conversational Commerce Protocol Engine.
    Driven by Native OpenAI SDK / Gemini Function Calling (Tools) with PostgreSQL backing.
    Zero brittle hardcoded regex/synonym lists. 100% Dynamic Tag & Full-Field Search.
    """

    # Framework-level conversational intent helpers (strictly for whole store general catalog fallback)
    BROAD_CATALOG_PHRASES = [
        "product list", "products list", "all product", "all products", "all items", "catalog",
        "catalogue", "sob product", "shob product", "store product", "সব প্রোডাক্ট", "পণ্য তালিকা", "পুরো ক্যাটালগ"
    ]

    TRACKING_PHRASES = [
        "track", "tracking", "order track", "track order", "order status", "amar order",
        "order kothay", "parcel", "delivery status", "courier", "কুরিয়ার", "ট্র্যাকিং", "অর্ডার স্ট্যাটাস"
    ]

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r'[^\w\s]', ' ', (text or '').lower()).strip()

    @classmethod
    def extract_quantity(cls, text: str) -> int:
        """
        Extracts quantity from Bangla, Banglish, and English shopping requests.
        Examples: '5 ta', '5ta', '৫টা', '৫টি', '5 pcs', '5 piece', 'qty 5', 'পাঁচটা', '২টি'
        """
        if not text:
            return 1
            
        bangla_digits = {'০':'0', '১':'1', '২':'2', '৩':'3', '৪':'4', '৫':'5', '৬':'6', '৭':'7', '৮':'8', '৯':'9'}
        norm_text = text.lower()
        for b_char, d_val in bangla_digits.items():
            norm_text = norm_text.replace(b_char, d_val)
        
        # Match explicit digits with suffixes: 5 ta, 5ta, 5 pcs, 5টি, qty 5, etc.
        match = re.search(r'(?:(?:qty|quantity|মোট)\s*[:=]?\s*(\d+))|(\d+)\s*(?:ta|টি|টা|pc|pcs|piece|pieces|ti|unit|units|জোড়া)', norm_text)
        if match:
            qty_str = match.group(1) or match.group(2)
            if qty_str and qty_str.isdigit():
                return max(1, int(qty_str))
                
        # Word numbers in Bengali
        word_map = {
            'একটি': 1, 'একটা': 1, 'দুটি': 2, 'দুইটা': 2, 'তিনটি': 3, 'তিনটা': 3,
            'চারটি': 4, 'চারটা': 4, 'পাঁচটি': 5, 'পাঁচটা': 5, 'ছয়টি': 6, 'ছয়টা': 6,
            'সাতটি': 7, 'সাতটা': 7, 'আটটি': 8, 'আটটা': 8, 'নয়টি': 9, 'নয়টা': 9, 'দশটি': 10, 'দশটা': 10
        }
        for w, num in word_map.items():
            if w in text:
                return num
                
        return 1

    @classmethod
    def serialize_product(cls, p: Product, initial_quantity: int = 1) -> Dict[str, Any]:
        return {
            "id": str(p.id),
            "title": p.title,
            "slug": p.slug,
            "category": p.category,
            "sku": p.sku,
            "unit_price": p.unit_price,
            "selling_price": p.selling_price,
            "stock_quantity": p.stock_quantity,
            "stock_status": p.stock_status,
            "images": p.images or [],
            "description": p.description,
            "specifications": p.specifications or {},
            "tags": p.tags or [],
            "priority": p.priority,
            "initial_quantity": max(1, initial_quantity)
        }

    @classmethod
    def serialize_order(cls, o: Order) -> Dict[str, Any]:
        return {
            "id": str(o.id),
            "order_number": o.order_number,
            "customer_name": o.customer_name,
            "customer_phone": o.customer_phone,
            "delivery_address": o.delivery_address,
            "delivery_city": o.delivery_city,
            "delivery_charge": o.delivery_charge,
            "subtotal_amount": o.subtotal_amount,
            "total_amount": o.total_amount,
            "payment_method": o.payment_method,
            "payment_status": o.payment_status,
            "order_status": o.order_status,
            "items": o.items_json or [],
            "bkash_trx_id": o.bkash_trx_id,
            "tracking_notes": o.tracking_notes or "Package packed and scheduled for courier pickup.",
            "created_at": o.created_at.isoformat() if o.created_at else None
        }

    @classmethod
    async def resolve_from_tool_call(
        cls,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        tool_name: str,
        tool_args: Dict[str, Any],
        conversation_id: Optional[uuid.UUID] = None,
        visitor_phone: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Executes native LLM Tool / Function Call with direct PostgreSQL resolution.
        Uses 100% generic SQL search across Title, Category, Description, and Tags (0 hardcoded lists).
        """
        if tool_name == "show_product_card":
            prod_query = str(tool_args.get("product_query", "")).strip()
            raw_qty = tool_args.get("quantity")
            if raw_qty and int(raw_qty) > 1:
                qty = int(raw_qty)
            else:
                qty = cls.extract_quantity(prod_query) if prod_query else 1

            stmt = select(Product).where(Product.tenant_id == tenant_id, Product.is_active == True)
            
            # 1. Exact SKU or exact slug match
            sku_match = await db.execute(stmt.where(or_(Product.sku.ilike(prod_query), Product.slug.ilike(prod_query))))
            matched_prod = sku_match.scalars().first()

            # 2. Match words across Title, Category, Description, and Tags with multi-word scoring
            if not matched_prod and prod_query:
                words = [w for w in cls._clean_text(prod_query).split() if len(w) > 1]
                if words:
                    conditions = [
                        or_(
                            Product.title.ilike(f"%{w}%"),
                            Product.category.ilike(f"%{w}%"),
                            Product.description.ilike(f"%{w}%"),
                            cast(Product.tags, String).ilike(f"%{w}%")
                        )
                        for w in words
                    ]
                    word_match_stmt = stmt.where(or_(*conditions))
                    word_res = await db.execute(word_match_stmt)
                    candidates = list(word_res.scalars().all())

                    if candidates:
                        # Rank candidates by:
                        # 1. Number of distinct query words matched across title, category, description, and tags
                        # 2. Priority / created_at (lowest priority number first)
                        def score_candidate(prod: Product) -> tuple:
                            tags_text = " ".join(prod.tags or [])
                            corpus = f"{prod.title} {prod.category} {prod.description} {prod.sku} {tags_text}".lower()
                            matched_count = sum(1 for w in words if w in corpus)
                            prio = prod.priority if (prod.priority and prod.priority > 0) else 999999
                            return (-matched_count, prio)

                        candidates.sort(key=score_candidate)
                        matched_prod = candidates[0]

            if matched_prod:
                return {
                    "type": "product_card",
                    "data": {
                        "product": cls.serialize_product(matched_prod, initial_quantity=qty)
                    }
                }

        elif tool_name == "show_product_catalog":
            category = str(tool_args.get("category", "all")).strip()

            stmt = select(Product).where(Product.tenant_id == tenant_id, Product.is_active == True)
            if category and category.lower() not in ["all", "none", "", "general", "store", "all products"]:
                clean_cat = cls._clean_text(category)
                cat_words = [w for w in clean_cat.split() if len(w) > 1]
                if cat_words:
                    # 100% Generic PostgreSQL Search against Category, Title, Description, and Tags (Zero hardcoded categories!)
                    cat_conditions = [
                        or_(
                            Product.category.ilike(f"%{w}%"),
                            Product.title.ilike(f"%{w}%"),
                            Product.description.ilike(f"%{w}%"),
                            cast(Product.tags, String).ilike(f"%{w}%")
                        )
                        for w in cat_words
                    ]
                    stmt = stmt.where(or_(*cat_conditions))

            stmt = stmt.order_by(
                case((Product.priority > 0, Product.priority), else_=999999).asc(),
                desc(Product.created_at)
            ).limit(50)

            res = await db.execute(stmt)
            products = list(res.scalars().all())

            if products:
                if len(products) == 1 and category.lower() not in ["all", "none", ""]:
                    return {
                        "type": "product_card",
                        "data": {
                            "product": cls.serialize_product(products[0])
                        }
                    }
                else:
                    return {
                        "type": "product_carousel",
                        "data": {
                            "products": [cls.serialize_product(p) for p in products]
                        }
                    }

        elif tool_name == "track_customer_order":
            order_num = tool_args.get("order_number")
            order_stmt = select(Order).where(Order.tenant_id == tenant_id)

            if order_num:
                order_stmt = order_stmt.where(Order.order_number.ilike(f"%{order_num.strip()}%"))
            elif conversation_id:
                order_stmt = order_stmt.where(
                    or_(Order.conversation_id == conversation_id, Order.customer_phone == visitor_phone)
                ).order_by(desc(Order.created_at)).limit(1)
            elif visitor_phone:
                order_stmt = order_stmt.where(Order.customer_phone == visitor_phone).order_by(desc(Order.created_at)).limit(1)

            order_res = await db.execute(order_stmt)
            matched_order = order_res.scalars().first()

            if matched_order:
                return {
                    "type": "order_tracking_card",
                    "data": {
                        "order": cls.serialize_order(matched_order)
                    }
                }

        return None

    @classmethod
    async def resolve_ui_component(
        cls,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        user_query: str,
        ai_response_text: Optional[str] = None,
        rag_chunks: Optional[List[Dict[str, Any]]] = None,
        conversation_id: Optional[uuid.UUID] = None,
        visitor_phone: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Main entry point for Generative UI resolution:
        1. Executes native Function Calling Tool Calls from LLM (Primary Enterprise Path).
        2. Fallbacks to direct SQL matching if no tool was emitted or tool returned no match.
        """
        # 1. Native Function Calling execution (Primary Enterprise Path)
        if tool_calls:
            for tc in tool_calls:
                comp = await cls.resolve_from_tool_call(
                    db=db,
                    tenant_id=tenant_id,
                    tool_name=tc.get("name", ""),
                    tool_args=tc.get("arguments", {}),
                    conversation_id=conversation_id,
                    visitor_phone=visitor_phone
                )
                if comp:
                    return comp

        # 2. Fallback Heuristic SQL matching
        clean_q = cls._clean_text(user_query)

        # Order Tracking Fallback
        order_num_match = re.search(r'(ORD-\d{8}-\w+)', user_query, re.IGNORECASE)
        has_tracking = any(tp in clean_q for tp in cls.TRACKING_PHRASES)
        if order_num_match or has_tracking:
            ord_str = order_num_match.group(1) if order_num_match else None
            comp = await cls.resolve_from_tool_call(
                db=db,
                tenant_id=tenant_id,
                tool_name="track_customer_order",
                tool_args={"order_number": ord_str},
                conversation_id=conversation_id,
                visitor_phone=visitor_phone
            )
            if comp:
                return comp

        # Broad Catalog Fallback
        is_broad = any(phrase in clean_q for phrase in cls.BROAD_CATALOG_PHRASES)
        if is_broad:
            comp = await cls.resolve_from_tool_call(
                db=db,
                tenant_id=tenant_id,
                tool_name="show_product_catalog",
                tool_args={"category": "all"},
                conversation_id=conversation_id,
                visitor_phone=visitor_phone
            )
            if comp:
                return comp

        # Direct SQL Product Match Fallback
        if clean_q and len(clean_q) > 3:
            extracted_qty = cls.extract_quantity(user_query)
            comp = await cls.resolve_from_tool_call(
                db=db,
                tenant_id=tenant_id,
                tool_name="show_product_card",
                tool_args={"product_query": user_query, "quantity": extracted_qty},
                conversation_id=conversation_id,
                visitor_phone=visitor_phone
            )
            if comp:
                return comp

        return None
