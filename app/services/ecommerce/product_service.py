import uuid
import re
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, delete, update, case
from datetime import datetime, timezone

from app.models.all_models import Product, KnowledgeBase, KnowledgeChunk
from app.schemas.schemas import ProductCreate, ProductUpdate
from app.services.ai.gemini import GeminiService

class ProductService:
    """
    SOLID Single-Responsibility Service for E-Commerce Product Management
    with Automatic Vector Embedding Sync to PostgreSQL 18 pgvector.
    Supports Smart Priority Auto-Shift Reordering for CDN Widget Display Order.
    """

    def __init__(self, db: AsyncSession, gemini_service: Optional[GeminiService] = None):
        self.db = db
        self.gemini = gemini_service or GeminiService()

    @staticmethod
    def slugify(text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r'[^\w\s-]', '', text)
        return re.sub(r'[\s_-]+', '-', text)[:250]

    def _generate_product_markdown(self, product: Product) -> str:
        specs_str = ""
        if product.specifications and isinstance(product.specifications, dict):
            specs_str = ", ".join([f"{k}: {v}" for k, v in product.specifications.items()])

        return (
            f"### Product Catalog: {product.title} [{product.category}]\n"
            f"- SKU: {product.sku or 'N/A'}\n"
            f"- Regular Price (MSRP): ৳{product.unit_price:,.2f} BDT\n"
            f"- Selling / Offer Price: ৳{product.selling_price:,.2f} BDT\n"
            f"- Stock Status: {product.stock_status.replace('_', ' ').title()} ({product.stock_quantity} units in stock)\n"
            f"- Description: {product.description or 'No extra description provided.'}\n"
            f"- Specifications: {specs_str or 'Standard'}"
        )

    async def _sync_product_vector(self, product: Product) -> None:
        """
        Automatically syncs product details to PostgreSQL 18 pgvector knowledge chunk
        so the AI chatbot has zero-latency live access to exact pricing and stock.
        """
        try:
            # 1. Ensure or find Product Catalog KnowledgeBase for this tenant
            kb_stmt = select(KnowledgeBase).where(
                KnowledgeBase.tenant_id == product.tenant_id,
                KnowledgeBase.title == "E-Commerce Live Products Catalog"
            )
            kb_res = await self.db.execute(kb_stmt)
            kb = kb_res.scalars().first()

            if not kb:
                kb = KnowledgeBase(
                    id=uuid.uuid4(),
                    tenant_id=product.tenant_id,
                    title="E-Commerce Live Products Catalog",
                    description="Auto-synchronized live product inventory, prices, and stock from Products module.",
                    category="Products",
                    source_type="product_catalog",
                    status="indexed",
                    chunk_count=0
                )
                self.db.add(kb)
                await self.db.flush()

            # 2. Check if chunk already exists for this product
            chunk_stmt = select(KnowledgeChunk).where(
                KnowledgeChunk.knowledge_base_id == kb.id,
                KnowledgeChunk.content.contains(f"Product Catalog: {product.title}")
            )
            chunk_res = await self.db.execute(chunk_stmt)
            chunk = chunk_res.scalars().first()

            product_text = self._generate_product_markdown(product)
            embedding_vector = await self.gemini.get_embedding(product_text)

            if chunk:
                chunk.content = product_text
                chunk.embedding_json = embedding_vector
                chunk.metadata_json = {
                    "product_id": str(product.id),
                    "selling_price": product.selling_price,
                    "unit_price": product.unit_price,
                    "stock_status": product.stock_status,
                    "category": product.category,
                    "images": product.images
                }
            else:
                new_chunk = KnowledgeChunk(
                    id=uuid.uuid4(),
                    knowledge_base_id=kb.id,
                    tenant_id=product.tenant_id,
                    content=product_text,
                    embedding_json=embedding_vector,
                    chunk_index=0,
                    metadata_json={
                        "product_id": str(product.id),
                        "selling_price": product.selling_price,
                        "unit_price": product.unit_price,
                        "stock_status": product.stock_status,
                        "category": product.category,
                        "images": product.images
                    }
                )
                self.db.add(new_chunk)
                kb.chunk_count = (kb.chunk_count or 0) + 1

            await self.db.flush()
        except Exception as e:
            # Vector sync is resilient and non-blocking
            print(f"[ProductService] Vector sync notice: {str(e)}", flush=True)

    async def _reorder_priorities(self, tenant_id: uuid.UUID, product_id: uuid.UUID, new_priority: int) -> None:
        """
        Smart Auto-Shift Priority Reorder Engine.

        When a product is assigned priority N, all other products with priority >= N
        are shifted up by 1 to maintain a gapless, non-duplicate priority sequence.

        Example: Assigning priority 1 to product X:
          Before: [A=1, B=2, C=3, X=10]
          After:  [X=1, A=2, B=3, C=4]

        Products with priority=0 are "unranked" and sorted by newest first (DESC created_at).
        """
        if new_priority <= 0:
            # Removing from ranked list: just set to 0, no cascade needed
            return

        # Shift all other ranked products that occupy >= new_priority slot upward
        await self.db.execute(
            update(Product)
            .where(
                Product.tenant_id == tenant_id,
                Product.id != product_id,
                Product.priority >= new_priority,
                Product.priority > 0
            )
            .values(priority=Product.priority + 1)
        )
        await self.db.flush()

    async def generate_ai_tags(
        self,
        title: str,
        category: str = "General",
        description: str = "",
        specifications: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """
        AI Auto-Tagger Engine using Gemini.
        Extracts 6 to 10 high-relevance multilingual search keywords & synonyms (Bengali, Banglish, English, product types).
        """
        import json
        specs_text = ", ".join([f"{k}: {v}" for k, v in (specifications or {}).items()]) if specifications else ""
        prompt = (
            f"You are an E-Commerce Product Search Tagging Engine.\n"
            f"Analyze the following product details and generate 6 to 10 high-precision search keywords and synonyms in a JSON array of strings.\n"
            f"Include:\n"
            f"1. Bengali words / spellings (e.g. ঘড়ি, পাঞ্জাবি, জুতা, শাড়ি, মধু)\n"
            f"2. Banglish & English keywords (e.g. smartwatch, watch, panjabi, shoes, sneakers)\n"
            f"3. Core category synonyms (e.g. electronics, footwear, fashion, audio)\n"
            f"4. Key product features or slang (e.g. wireless, fast charging, pure cotton)\n\n"
            f"Product Title: {title}\n"
            f"Category: {category}\n"
            f"Description: {description or 'N/A'}\n"
            f"Specifications: {specs_text or 'N/A'}\n\n"
            f"Output ONLY a raw JSON array of strings, for example:\n"
            f"[\"smartwatch\", \"watch\", \"ঘড়ি\", \"স্মার্টওয়াচ\", \"fitness tracker\", \"gadget\"]"
        )
        try:
            res = await self.gemini.client.chat.completions.create(
                model="gemini-1.5-flash",
                messages=[
                    {"role": "system", "content": "You are a concise e-commerce search tag extraction AI. Respond with ONLY a JSON array of strings."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=200
            )
            raw = res.choices[0].message.content or "[]"
            raw = re.sub(r'```(?:json)?', '', raw).strip()
            tags = json.loads(raw)
            if isinstance(tags, list):
                cleaned = []
                for t in tags:
                    clean_t = str(t).strip().lower()
                    if clean_t and clean_t not in cleaned:
                        cleaned.append(clean_t)
                return cleaned[:12]
        except Exception as e:
            print(f"[ProductService] Tag generation notice: {str(e)}", flush=True)

        base = [w.lower() for w in re.sub(r'[^\w\s]', ' ', title).split() if len(w) > 2]
        if category and category.lower() not in base:
            base.append(category.lower())
        return list(set(base))

    async def create_product(self, tenant_id: uuid.UUID, data: ProductCreate) -> Product:
        slug_candidate = self.slugify(data.title)
        slug = f"{slug_candidate}-{uuid.uuid4().hex[:6]}"

        # Resolve priority: if a positive priority is requested, auto-shift others first
        if data.priority and data.priority > 0:
            await self._reorder_priorities(tenant_id, uuid.UUID("00000000-0000-0000-0000-000000000000"), data.priority)

        # AI Auto-Tagging: if tags is empty, automatically generate from title & description
        tags = list(data.tags or [])
        if not tags:
            tags = await self.generate_ai_tags(
                title=data.title,
                category=data.category,
                description=data.description or "",
                specifications=data.specifications or {}
            )

        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            title=data.title,
            slug=slug,
            category=data.category,
            sku=data.sku or f"SKU-{uuid.uuid4().hex[:8].upper()}",
            unit_price=data.unit_price,
            selling_price=data.selling_price if data.selling_price > 0 else data.unit_price,
            stock_quantity=data.stock_quantity,
            stock_status=data.stock_status,
            images=data.images,
            description=data.description,
            specifications=data.specifications or {},
            tags=tags,
            is_active=data.is_active,
            priority=data.priority or 0
        )
        self.db.add(product)
        await self.db.flush()

        # Auto sync vector embeddings
        await self._sync_product_vector(product)
        await self.db.commit()
        await self.db.refresh(product)
        return product

    async def update_product(self, product_id: uuid.UUID, tenant_id: uuid.UUID, data: ProductUpdate) -> Optional[Product]:
        stmt = select(Product).where(Product.id == product_id, Product.tenant_id == tenant_id)
        res = await self.db.execute(stmt)
        product = res.scalars().first()
        if not product:
            return None

        update_dict = data.model_dump(exclude_unset=True)

        # Handle priority auto-shift before applying update
        if "priority" in update_dict and update_dict["priority"] is not None:
            new_priority = update_dict["priority"]
            if new_priority > 0:
                await self._reorder_priorities(tenant_id, product_id, new_priority)

        # If tags field is passed as empty list, trigger AI auto-tagging
        if "tags" in update_dict and (update_dict["tags"] is None or len(update_dict["tags"]) == 0):
            update_dict["tags"] = await self.generate_ai_tags(
                title=update_dict.get("title", product.title),
                category=update_dict.get("category", product.category),
                description=update_dict.get("description", product.description or ""),
                specifications=update_dict.get("specifications", product.specifications or {})
            )

        for k, v in update_dict.items():
            setattr(product, k, v)

        if "title" in update_dict and update_dict["title"]:
            product.slug = f"{self.slugify(update_dict['title'])}-{uuid.uuid4().hex[:6]}"

        await self.db.flush()
        await self._sync_product_vector(product)
        await self.db.commit()
        await self.db.refresh(product)
        return product

    async def delete_product(self, product_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
        stmt = select(Product).where(Product.id == product_id, Product.tenant_id == tenant_id)
        res = await self.db.execute(stmt)
        product = res.scalars().first()
        if not product:
            return False

        # Delete associated vector chunk
        await self.db.execute(
            delete(KnowledgeChunk).where(
                KnowledgeChunk.tenant_id == tenant_id,
                KnowledgeChunk.content.contains(f"Product Catalog: {product.title}")
            )
        )
        await self.db.delete(product)
        await self.db.commit()
        return True

    async def get_products(
        self,
        tenant_id: uuid.UUID,
        category: Optional[str] = None,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        sort_by: Optional[str] = None,    # "title", "selling_price", "stock_quantity", "priority", "created_at"
        sort_dir: Optional[str] = "desc", # "asc" or "desc"
        limit: int = 50,
        offset: int = 0
    ) -> List[Product]:
        stmt = select(Product).where(Product.tenant_id == tenant_id)
        if category:
            stmt = stmt.where(Product.category == category)
        if search:
            stmt = stmt.where(
                Product.title.ilike(f"%{search}%") |
                Product.sku.ilike(f"%{search}%") |
                Product.category.ilike(f"%{search}%")
            )
        if is_active is not None:
            stmt = stmt.where(Product.is_active == is_active)

        # Smart Priority-First Ordering:
        # Ranked products (priority > 0) shown first in ASC order (1 = top),
        # then unranked products (priority = 0) sorted by user-specified or default (newest first).
        asc_map = {"asc": True, "desc": False}
        is_asc = asc_map.get((sort_dir or "desc").lower(), False)

        if sort_by == "title":
            col = Product.title
            stmt = stmt.order_by(
                case((Product.priority > 0, Product.priority), else_=999999),
                col.asc() if is_asc else col.desc()
            )
        elif sort_by == "selling_price":
            col = Product.selling_price
            stmt = stmt.order_by(
                case((Product.priority > 0, Product.priority), else_=999999),
                col.asc() if is_asc else col.desc()
            )
        elif sort_by == "stock_quantity":
            col = Product.stock_quantity
            stmt = stmt.order_by(
                case((Product.priority > 0, Product.priority), else_=999999),
                col.asc() if is_asc else col.desc()
            )
        elif sort_by == "priority":
            # Direct priority sort, asc=1,2,3..., desc=999,998...
            if is_asc:
                stmt = stmt.order_by(
                    case((Product.priority > 0, Product.priority), else_=999999).asc(),
                    desc(Product.created_at)
                )
            else:
                stmt = stmt.order_by(
                    case((Product.priority > 0, Product.priority), else_=0).desc(),
                    desc(Product.created_at)
                )
        else:
            # Default: priority-first (1 is top), then newest first for unranked
            stmt = stmt.order_by(
                case((Product.priority > 0, Product.priority), else_=999999).asc(),
                desc(Product.created_at)
            )

        stmt = stmt.limit(limit).offset(offset)
        res = await self.db.execute(stmt)
        return list(res.scalars().all())
