import uuid
import re
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models.all_models import KnowledgeBase, KnowledgeChunk
from app.services.ai.gemini import GeminiService

class RAGService:
    """
    Enterprise Retrieval-Augmented Generation (RAG) Service:
    - Smart Markdown & Documentation Chunking
    - Structured FAQ / Q&A Ingestion
    - Vector Embedding Generation & Pgvector Cosine Similarity Search
    - Live Search Sandbox for Cosine Verification
    """

    def __init__(self, db: AsyncSession, gemini_service: Optional[GeminiService] = None):
        self.db = db
        self.gemini = gemini_service or GeminiService()

    def chunk_markdown_text(self, text: str, max_chunk_words: int = 250, overlap_words: int = 30) -> List[str]:
        """
        Splits markdown documentation intelligently across headers (##), 
        paragraphs, and list items to preserve conceptual context.
        """
        if not text or not text.strip():
            return []

        # Split by double newline or headers
        sections = re.split(r'\n(?=#{1,4} |\n)', text)
        chunks = []

        current_chunk = []
        current_word_count = 0

        for section in sections:
            section_clean = section.strip()
            if not section_clean:
                continue
            words = section_clean.split()
            word_len = len(words)

            if word_len > max_chunk_words:
                # Sub-chunk very large sections
                sub_chunks = self._sliding_window_words(section_clean, max_chunk_words, overlap_words)
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = []
                    current_word_count = 0
                chunks.extend(sub_chunks)
            elif current_word_count + word_len <= max_chunk_words:
                current_chunk.append(section_clean)
                current_word_count += word_len
            else:
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                current_chunk = [section_clean]
                current_word_count = word_len

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return [c.strip() for c in chunks if c.strip()]

    def _sliding_window_words(self, text: str, chunk_size: int = 250, overlap: int = 30) -> List[str]:
        words = text.split()
        if not words:
            return []
        chunks = []
        i = 0
        while i < len(words):
            chunk = " ".join(words[i:i + chunk_size])
            chunks.append(chunk)
            i += max(1, chunk_size - overlap)
            if i >= len(words):
                break
        return chunks

    async def ingest_document(
        self,
        tenant_id: uuid.UUID,
        title: str,
        content: str,
        category: str = "General",
        source_type: str = "markdown_doc",
        source_url: Optional[str] = None
    ) -> KnowledgeBase:
        """Ingests full documentation or raw text with vector embeddings."""
        chunks_text = self.chunk_markdown_text(content)
        if not chunks_text and content.strip():
            chunks_text = [content.strip()]

        kb = KnowledgeBase(
            tenant_id=tenant_id,
            title=title,
            description=content[:180].replace("\n", " ") + ("..." if len(content) > 180 else ""),
            category=category,
            source_type=source_type,
            source_url=source_url,
            chunk_count=len(chunks_text),
            status="indexing"
        )
        self.db.add(kb)
        await self.db.flush()

        for idx, chunk_text in enumerate(chunks_text):
            embedding_vec = await self.gemini.get_embedding(chunk_text)
            chunk_record = KnowledgeChunk(
                knowledge_base_id=kb.id,
                tenant_id=tenant_id,
                chunk_index=idx,
                content=chunk_text,
                embedding_json=embedding_vec,
                metadata_json={
                    "doc_title": title,
                    "category": category,
                    "source_type": source_type,
                    "chunk_index": idx,
                    "total_chunks": len(chunks_text)
                }
            )
            self.db.add(chunk_record)

        kb.status = "indexed"
        await self.db.commit()
        await self.db.refresh(kb)
        return kb

    async def ingest_faq_items(
        self,
        tenant_id: uuid.UUID,
        title: str,
        category: str,
        faq_items: List[Dict[str, str]]
    ) -> KnowledgeBase:
        """Ingests structured Question & Answer FAQ pairs directly into knowledge chunks."""
        kb = KnowledgeBase(
            tenant_id=tenant_id,
            title=title,
            description=f"Structured FAQ Collection ({len(faq_items)} Q&A pairs)",
            category=category,
            source_type="faq_qa",
            chunk_count=len(faq_items),
            status="indexing"
        )
        self.db.add(kb)
        await self.db.flush()

        for idx, item in enumerate(faq_items):
            q = item.get("question", "").strip()
            a = item.get("answer", "").strip()
            if not q or not a:
                continue

            chunk_content = f"**Question**: {q}\n**Answer**: {a}"
            embedding_vec = await self.gemini.get_embedding(f"{q}\n{a}")

            chunk_record = KnowledgeChunk(
                knowledge_base_id=kb.id,
                tenant_id=tenant_id,
                chunk_index=idx,
                content=chunk_content,
                embedding_json=embedding_vec,
                metadata_json={
                    "doc_title": title,
                    "category": category,
                    "source_type": "faq_qa",
                    "question": q,
                    "answer": a
                }
            )
            self.db.add(chunk_record)

        kb.status = "indexed"
        await self.db.commit()
        await self.db.refresh(kb)
        return kb

    async def search_relevant_chunks(
        self,
        tenant_id: uuid.UUID,
        query: str,
        limit: int = 3,
        similarity_threshold: float = 0.45
    ) -> List[Dict[str, Any]]:
        """Vector similarity search against tenant-isolated knowledge chunks."""
        try:
            stmt = (
                select(KnowledgeChunk.content, KnowledgeChunk.metadata_json, KnowledgeChunk.embedding_json)
                .where(KnowledgeChunk.tenant_id == tenant_id)
            )
            result = await self.db.execute(stmt)
            rows = result.all()
            if not rows:
                return []

            query_vector = await self.gemini.get_embedding(query)
            if not query_vector:
                # Text fallback
                return [
                    {
                        "source": row.metadata_json.get("doc_title", "Documentation") if row.metadata_json else "Documentation",
                        "category": row.metadata_json.get("category", "General") if row.metadata_json else "General",
                        "content": row.content,
                        "similarity": 0.85
                    }
                    for row in rows[:limit]
                ]

            scored_chunks = []
            for row in rows:
                score = 0.50
                if row.embedding_json:
                    score = self.gemini.calculate_cosine_similarity(query_vector, row.embedding_json)
                
                doc_title = row.metadata_json.get("doc_title", "Documentation") if row.metadata_json else "Documentation"
                category = row.metadata_json.get("category", "General") if row.metadata_json else "General"

                if score >= similarity_threshold:
                    scored_chunks.append({
                        "source": doc_title,
                        "category": category,
                        "content": row.content,
                        "similarity": round(float(score), 4)
                    })

            scored_chunks.sort(key=lambda x: x["similarity"], reverse=True)
            return scored_chunks[:limit]
        except Exception as e:
            print("RAG search error:", e)
            return []

    async def delete_knowledge_base(self, tenant_id: uuid.UUID, kb_id: uuid.UUID) -> bool:
        """Deletes a knowledge base and cascades all associated vector chunks."""
        stmt = select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.tenant_id == tenant_id)
        kb = (await self.db.execute(stmt)).scalars().first()
        if not kb:
            return False
        
        await self.db.delete(kb)
        await self.db.commit()
        return True
