import uuid
import re
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, delete
from datetime import datetime, timezone

from app.models.all_models import Product, KnowledgeBase, KnowledgeChunk
from app.schemas.schemas import ProductCreate, ProductUpdate
from app.services.ai.gemini import GeminiService

class ProductService:
    """
    SOLID Single-Responsibility Service for E-Commerce Product Management
    with Automatic Vector Embedding Sync to PostgreSQL 18 pgvector.
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

    async def create_product(self, tenant_id: uuid.UUID, data: ProductCreate) -> Product:
        slug_candidate = self.slugify(data.title)
        slug = f"{slug_candidate}-{uuid.uuid4().hex[:6]}"

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
            is_active=data.is_active
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
        limit: int = 50,
        offset: int = 0
    ) -> List[Product]:
        stmt = select(Product).where(Product.tenant_id == tenant_id)
        if category:
            stmt = stmt.where(Product.category == category)
        if search:
            stmt = stmt.where(Product.title.ilike(f"%{search}%"))
        if is_active is not None:
            stmt = stmt.where(Product.is_active == is_active)

        stmt = stmt.order_by(desc(Product.created_at)).limit(limit).offset(offset)
        res = await self.db.execute(stmt)
        return list(res.scalars().all())
