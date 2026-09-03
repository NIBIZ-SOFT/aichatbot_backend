import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import encrypt_secret
from app.api.v1.auth import get_current_user
from app.models.all_models import Tenant, AIAssistant, KnowledgeBase, Website, User, UserRole
from app.schemas.schemas import (
    TenantOut, TenantUpdate,
    AIAssistantCreate, AIAssistantUpdate, AIAssistantOut,
    KnowledgeBaseCreate, KnowledgeBaseOut,
    KnowledgeIngestText, KnowledgeIngestFAQ, KnowledgeSearchSandbox, KnowledgeSearchResult,
    TestChatPayload,
    WebsiteCreate, WebsiteUpdate, WebsiteOut
)
from app.services.rag.rag_service import RAGService
from app.services.ai.safety_rules import AISafetyAndRulesEngine

router = APIRouter(tags=["Tenant & AI Management"])

# ----------------- TENANT PROFILE & SETTINGS -----------------
@router.get("/tenant/current", response_model=TenantOut)
@router.get("/tenant", response_model=TenantOut)
async def get_tenant_info(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="User does not belong to a tenant")
    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant

@router.patch("/tenant/settings", response_model=TenantOut)
@router.patch("/settings", response_model=TenantOut)
async def update_tenant_settings(
    payload: TenantUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="User does not belong to a tenant")
    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant organization not found")
    
    from sqlalchemy.orm.attributes import flag_modified

    if payload.name is not None:
        tenant.name = payload.name
    if payload.custom_domain is not None:
        tenant.custom_domain = payload.custom_domain
    if payload.whitelabel_enabled is not None:
        tenant.whitelabel_enabled = payload.whitelabel_enabled
    if payload.branding_config is not None:
        current_config = dict(tenant.branding_config or {})
        current_config.update(payload.branding_config)
        tenant.branding_config = current_config
        flag_modified(tenant, "branding_config")

    await db.commit()
    await db.refresh(tenant)
    return tenant

# ----------------- AI ASSISTANTS -----------------
@router.post("/assistants", response_model=AIAssistantOut)
@router.post("/tenant/assistants", response_model=AIAssistantOut)
async def create_assistant(
    payload: AIAssistantCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    assistant = AIAssistant(
        tenant_id=user.tenant_id,
        name=payload.name,
        description=payload.description,
        model_name=payload.model_name,
        temperature=payload.temperature,
        top_p=payload.top_p,
        max_output_tokens=payload.max_output_tokens,
        system_instruction=payload.system_instruction,
        fallback_message=payload.fallback_message,
        auto_handover_keywords=payload.auto_handover_keywords,
        safety_settings=payload.safety_settings or {}
    )
    db.add(assistant)
    await db.commit()
    await db.refresh(assistant)
    return assistant

@router.patch("/assistants/{assistant_id}", response_model=AIAssistantOut)
async def update_assistant(
    assistant_id: uuid.UUID,
    payload: AIAssistantUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(AIAssistant).where(AIAssistant.id == assistant_id, AIAssistant.tenant_id == user.tenant_id)
    assistant = (await db.execute(stmt)).scalars().first()
    if not assistant:
        raise HTTPException(status_code=404, detail="Assistant not found")
    
    if payload.name is not None:
        assistant.name = payload.name
    if payload.description is not None:
        assistant.description = payload.description
    if payload.personality_type is not None:
        assistant.personality_type = payload.personality_type
    if payload.model_name is not None:
        assistant.model_name = payload.model_name
    if payload.temperature is not None:
        assistant.temperature = payload.temperature
    if payload.top_p is not None:
        assistant.top_p = payload.top_p
    if payload.max_output_tokens is not None:
        assistant.max_output_tokens = payload.max_output_tokens
    if payload.system_instruction is not None:
        assistant.system_instruction = payload.system_instruction
    if payload.fallback_message is not None:
        assistant.fallback_message = payload.fallback_message
    if payload.auto_handover_keywords is not None:
        assistant.auto_handover_keywords = payload.auto_handover_keywords
    if payload.safety_settings is not None:
        assistant.safety_settings = payload.safety_settings
    if payload.is_active is not None:
        assistant.is_active = payload.is_active

    await db.commit()
    await db.refresh(assistant)
    return assistant

@router.get("/assistants", response_model=List[AIAssistantOut])
@router.get("/tenant/assistants", response_model=List[AIAssistantOut])
async def list_assistants(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(AIAssistant).where(AIAssistant.tenant_id == user.tenant_id))
    return result.scalars().all()

@router.patch("/assistants/{assistant_id}/toggle")
async def toggle_assistant_active(
    assistant_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(AIAssistant).where(AIAssistant.id == assistant_id, AIAssistant.tenant_id == user.tenant_id)
    assistant = (await db.execute(stmt)).scalars().first()
    if not assistant:
        raise HTTPException(status_code=404, detail="Assistant not found")
    assistant.is_active = not assistant.is_active
    await db.commit()
    await db.refresh(assistant)
    return {"status": "success", "assistant_id": assistant.id, "is_active": assistant.is_active}

# ----------------- KNOWLEDGE & RAG INGESTION -----------------
@router.post("/knowledge", response_model=KnowledgeBaseOut)
@router.post("/knowledge/ingest-text", response_model=KnowledgeBaseOut)
async def ingest_knowledge_text(
    payload: KnowledgeIngestText,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    rag = RAGService(db=db)
    kb = await rag.ingest_document(
        tenant_id=user.tenant_id,
        title=payload.title,
        content=payload.content,
        category=payload.category,
        source_type=payload.source_type,
        source_url=payload.source_url
    )
    return kb

@router.post("/knowledge/ingest-faq", response_model=KnowledgeBaseOut)
async def ingest_knowledge_faq(
    payload: KnowledgeIngestFAQ,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    rag = RAGService(db=db)
    items = [{"question": item.question, "answer": item.answer} for item in payload.faq_items]
    kb = await rag.ingest_faq_items(
        tenant_id=user.tenant_id,
        title=payload.title,
        category=payload.category,
        faq_items=items
    )
    return kb

@router.post("/knowledge/search-sandbox", response_model=List[KnowledgeSearchResult])
async def search_knowledge_sandbox(
    payload: KnowledgeSearchSandbox,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    rag = RAGService(db=db)
    results = await rag.search_relevant_chunks(
        tenant_id=user.tenant_id,
        query=payload.query,
        limit=payload.limit or 4,
        similarity_threshold=0.30
    )
    return results

@router.post("/knowledge/test-chat")
async def test_ai_chat_simulator(
    payload: TestChatPayload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Live AI Chat Simulator for business owners to test their bot's pre-trained knowledge,
    personality, system instructions, and RAG retrieval in real-time.
    """
    message = payload.message
    assistant_id = payload.assistant_id

    # 1. Fetch Tenant and Assistant Settings
    tenant_res = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = tenant_res.scalars().first()
    company_name = tenant.name if tenant else "Our Business"

    stmt = select(AIAssistant).where(AIAssistant.tenant_id == user.tenant_id)
    if assistant_id:
        try:
            stmt = stmt.where(AIAssistant.id == uuid.UUID(str(assistant_id)))
        except Exception:
            pass
    asst_res = await db.execute(stmt)
    asst = asst_res.scalars().first()

    raw_system_instruction = asst.system_instruction if asst else "You are a helpful customer support AI assistant."
    model_name = asst.model_name if asst else "gemini-1.5-flash"
    temperature = asst.temperature if asst else 0.3
    max_tokens = asst.max_output_tokens if asst else 1024
    safety_settings = asst.safety_settings if asst else {}
    guardrails_cfg = safety_settings.get("guardrails", {}) if isinstance(safety_settings, dict) else {}

    # 0. Fast Zero-Token Pre-Flight Check in Simulator
    is_preflight_off_topic, reason = AISafetyAndRulesEngine.pre_flight_off_topic_check(
        user_message=message,
        guardrails_cfg=guardrails_cfg
    )
    if is_preflight_off_topic:
        warning_msg = guardrails_cfg.get(
            "warning_message",
            f"I specialize in assisting with {company_name}'s products, orders, and pricing. How can I help with your inquiry today?"
        )
        return {
            "reply": warning_msg,
            "model": "pre-flight-zero-token-guardrail",
            "is_off_topic": True,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "retrieved_sources": [],
            "latency_ms": 2
        }

    # Build Guarded System Prompt via AISafetyAndRulesEngine
    guarded_prompt, is_guardrails_enabled, guardrails_cfg = AISafetyAndRulesEngine.build_guarded_prompt(
        raw_system_prompt=raw_system_instruction,
        company_name=company_name,
        visitor_name="Simulator Visitor",
        department="AI Simulator",
        safety_settings=safety_settings
    )

    # 2. Retrieve Relevant Knowledge Chunks via pgvector
    rag = RAGService(db=db)
    chunks = await rag.search_relevant_chunks(
        tenant_id=user.tenant_id,
        query=message,
        limit=3,
        similarity_threshold=0.20
    )

    context_text = ""
    retrieved_sources = []
    if chunks:
        context_text = "\n\nRelevant Business Knowledge:\n" + "\n---\n".join([f"[{c.get('source', 'Knowledge')}]: {c.get('content', '')}" for c in chunks])
        retrieved_sources = [{"title": c.get("source", "Knowledge"), "similarity": round(float(c.get("similarity", 0.0)), 2), "content": c.get("content", "")} for c in chunks]

    # 3. Call Gemini AI Engine with Augmented Context & Guardrails
    from app.services.ai.gemini import GeminiService
    gemini_svc = GeminiService()
    
    ai_response = await gemini_svc.generate_chat_response(
        system_instruction=guarded_prompt,
        chat_history=[],
        user_message=message,
        rag_context=context_text,
        model=model_name,
        temperature=temperature,
        max_output_tokens=max_tokens
    )

    raw_reply = ai_response.get("text", "I am here to help you with your inquiry.")
    
    # Process Guardrail Evaluation
    evaluated = AISafetyAndRulesEngine.evaluate_guardrail_response(
        ai_reply_text=raw_reply,
        guardrails_cfg=guardrails_cfg,
        current_strikes=0
    )

    final_reply = evaluated["text"]

    return {
        "reply": final_reply,
        "model": model_name,
        "is_off_topic": evaluated["is_off_topic"],
        "prompt_tokens": ai_response.get("prompt_tokens", 0),
        "completion_tokens": ai_response.get("completion_tokens", 0),
        "retrieved_sources": retrieved_sources if not evaluated["is_off_topic"] else [],
        "latency_ms": ai_response.get("latency_ms", 350)
    }

@router.delete("/knowledge/{knowledge_id}")
async def delete_knowledge_document(
    knowledge_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    rag = RAGService(db=db)
    success = await rag.delete_knowledge_base(tenant_id=user.tenant_id, kb_id=knowledge_id)
    if not success:
        raise HTTPException(status_code=404, detail="Knowledge base document not found")
    return {"status": "success", "message": "Knowledge document and all vector chunks deleted from PostgreSQL"}

@router.get("/knowledge", response_model=List[KnowledgeBaseOut])
@router.get("/tenant/knowledge", response_model=List[KnowledgeBaseOut])
async def list_knowledge_docs(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(KnowledgeBase)
        .where(KnowledgeBase.tenant_id == user.tenant_id)
        .order_by(KnowledgeBase.created_at.desc())
    )
    return result.scalars().all()

# ----------------- WIDGET / WEBSITE CREATION & MANAGEMENT -----------------
@router.post("/widgets", response_model=WebsiteOut)
@router.post("/websites", response_model=WebsiteOut)
async def create_widget(
    payload: WebsiteCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Ensure user has an active tenant_id
    if not user.tenant_id:
        if user.role == UserRole.SUPER_ADMIN:
            from app.api.v1.conversations import ensure_platform_live_support_widget
            support_widget = await ensure_platform_live_support_widget(db)
            if support_widget:
                user.tenant_id = support_widget.tenant_id
                await db.commit()
                await db.refresh(user)
        if not user.tenant_id:
            raise HTTPException(status_code=400, detail="User does not belong to an active organization/tenant")

    # Resolve assistant_id if not explicitly provided
    assistant_id = payload.assistant_id
    if not assistant_id:
        asst_stmt = select(AIAssistant).where(AIAssistant.tenant_id == user.tenant_id, AIAssistant.is_active == True)
        asst = (await db.execute(asst_stmt)).scalars().first()
        if asst:
            assistant_id = asst.id

    widget_key = f"wgt_{uuid.uuid4().hex[:18]}"
    site = Website(
        tenant_id=user.tenant_id,
        assistant_id=assistant_id,
        widget_key=widget_key,
        name=payload.name,
        domain=payload.domain,
        primary_color=payload.primary_color,
        header_title=payload.header_title,
        welcome_message=payload.welcome_message,
        position=payload.position,
        business_category=payload.business_category or "ecommerce",
        ecommerce_config=payload.ecommerce_config or {},
        branding_config=payload.branding_config or {}
    )
    db.add(site)
    await db.commit()
    await db.refresh(site)
    return site

@router.patch("/widgets/{website_id}", response_model=WebsiteOut)
@router.patch("/websites/{website_id}", response_model=WebsiteOut)
@router.put("/websites/{website_id}", response_model=WebsiteOut)
async def update_widget(
    website_id: uuid.UUID,
    payload: WebsiteUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    site_stmt = select(Website).where(Website.id == website_id)
    if user.role != UserRole.SUPER_ADMIN:
        site_stmt = site_stmt.where(Website.tenant_id == user.tenant_id)
    
    res = await db.execute(site_stmt)
    site = res.scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Website widget not found")

    if payload.name is not None:
        site.name = payload.name
    if payload.domain is not None:
        site.domain = payload.domain
    if payload.assistant_id is not None:
        site.assistant_id = payload.assistant_id
    if payload.primary_color is not None:
        site.primary_color = payload.primary_color
    if payload.header_title is not None:
        site.header_title = payload.header_title
    if payload.welcome_message is not None:
        site.welcome_message = payload.welcome_message
    if payload.position is not None:
        site.position = payload.position
    if payload.business_category is not None:
        site.business_category = payload.business_category
    if payload.ecommerce_config is not None:
        from sqlalchemy.orm.attributes import flag_modified
        cur_ecom = dict(site.ecommerce_config or {})
        cur_ecom.update(payload.ecommerce_config)
        site.ecommerce_config = cur_ecom
        flag_modified(site, "ecommerce_config")
    if payload.branding_config is not None:
        from sqlalchemy.orm.attributes import flag_modified
        cur_brand = dict(site.branding_config or {})
        cur_brand.update(payload.branding_config)
        site.branding_config = cur_brand
        flag_modified(site, "branding_config")
    if payload.is_active is not None:
        site.is_active = payload.is_active

    await db.commit()
    await db.refresh(site)
    return site

@router.delete("/widgets/{website_id}")
@router.delete("/websites/{website_id}")
async def delete_widget(
    website_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    site_stmt = select(Website).where(Website.id == website_id)
    if user.role != UserRole.SUPER_ADMIN:
        site_stmt = site_stmt.where(Website.tenant_id == user.tenant_id)

    res = await db.execute(site_stmt)
    site = res.scalars().first()
    if not site:
        raise HTTPException(status_code=404, detail="Website widget not found")

    # Prevent deleting platform support widget
    if site.widget_key == "wgt_platform_live_support":
        raise HTTPException(status_code=400, detail="Cannot delete the official platform live support widget")

    await db.delete(site)
    await db.commit()
    return {"status": "success", "message": "Website widget deleted successfully"}

@router.get("/widgets", response_model=List[WebsiteOut])
@router.get("/websites", response_model=List[WebsiteOut])
async def list_widgets(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not user.tenant_id:
        if user.role == UserRole.SUPER_ADMIN:
            from app.api.v1.conversations import ensure_platform_live_support_widget
            support_widget = await ensure_platform_live_support_widget(db)
            if support_widget:
                user.tenant_id = support_widget.tenant_id
                await db.commit()
                await db.refresh(user)
        else:
            return []

    result = await db.execute(
        select(Website)
        .where(Website.tenant_id == user.tenant_id)
        .order_by(Website.created_at.desc())
    )
    return result.scalars().all()
