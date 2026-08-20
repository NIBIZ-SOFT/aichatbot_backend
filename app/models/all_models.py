import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    String, Boolean, Integer, Text, DateTime, ForeignKey, 
    Enum, JSON, Float, Index, UniqueConstraint, Uuid
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
import enum

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    TENANT_OWNER = "tenant_owner"
    TENANT_ADMIN = "tenant_admin"
    SUPPORT_AGENT = "support_agent"
    SALES_AGENT = "sales_agent"
    MEMBER = "member"
    VIEWER = "viewer"

class SubscriptionTier(str, enum.Enum):
    FREE = "free"
    STARTER = "starter"
    GROWTH = "growth"
    ENTERPRISE = "enterprise"

class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    CANCELED = "canceled"

class ConversationStatus(str, enum.Enum):
    AI_ACTIVE = "ai_active"
    HUMAN_ACTIVE = "human_active"
    PENDING_AGENT = "pending_agent"
    RESOLVED = "resolved"
    CLOSED = "closed"

class ConversationPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class SenderType(str, enum.Enum):
    VISITOR = "visitor"
    AI = "ai"
    AGENT = "agent"
    SYSTEM = "system"

# ----------------- LAYER 1: SAAS CORE MODELS -----------------

class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    custom_domain: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    
    # White-label settings
    whitelabel_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    branding_config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Dynamic Feature Flags / Module Permissions (Per-Tenant Customization)
    business_category: Mapped[str] = mapped_column(String(50), default="ecommerce")
    enabled_modules: Mapped[Dict[str, bool]] = mapped_column(JSON, default=dict)
    ecommerce_settings: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    # Encrypted BYOK Gemini Key
    encrypted_gemini_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    users: Mapped[List["User"]] = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    subscriptions: Mapped[List["Subscription"]] = relationship("Subscription", back_populates="tenant", cascade="all, delete-orphan")
    api_keys: Mapped[List["ApiKey"]] = relationship("ApiKey", back_populates="tenant", cascade="all, delete-orphan")
    usage_records: Mapped[List["UsageRecord"]] = relationship("UsageRecord", back_populates="tenant", cascade="all, delete-orphan")
    assistants: Mapped[List["AIAssistant"]] = relationship("AIAssistant", back_populates="tenant", cascade="all, delete-orphan")
    knowledge_bases: Mapped[List["KnowledgeBase"]] = relationship("KnowledgeBase", back_populates="tenant", cascade="all, delete-orphan")
    websites: Mapped[List["Website"]] = relationship("Website", back_populates="tenant", cascade="all, delete-orphan")
    contacts: Mapped[List["Contact"]] = relationship("Contact", back_populates="tenant", cascade="all, delete-orphan")
    conversations: Mapped[List["Conversation"]] = relationship("Conversation", back_populates="tenant", cascade="all, delete-orphan")
    notifications: Mapped[List["Notification"]] = relationship("Notification", back_populates="tenant", cascade="all, delete-orphan")
    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="tenant", cascade="all, delete-orphan")
    products: Mapped[List["Product"]] = relationship("Product", back_populates="tenant", cascade="all, delete-orphan")
    orders: Mapped[List["Order"]] = relationship("Order", back_populates="tenant", cascade="all, delete-orphan")

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.MEMBER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant", back_populates="users")
    assigned_conversations: Mapped[List["Conversation"]] = relationship("Conversation", back_populates="assigned_agent")

class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    tier: Mapped[SubscriptionTier] = mapped_column(Enum(SubscriptionTier), default=SubscriptionTier.FREE)
    plan_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True) # e.g. 'starter', 'eid_mega_2026'
    status: Mapped[SubscriptionStatus] = mapped_column(Enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE)
    
    monthly_token_limit: Mapped[int] = mapped_column(Integer, default=500_000)
    monthly_conversation_limit: Mapped[int] = mapped_column(Integer, default=200)
    max_agents: Mapped[int] = mapped_column(Integer, default=2)
    max_websites: Mapped[int] = mapped_column(Integer, default=1)
    max_knowledge_docs: Mapped[int] = mapped_column(Integer, default=10)
    
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="subscriptions")

class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    hashed_key: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    scopes: Mapped[List[str]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="api_keys")

class Webhook(Base):
    __tablename__ = "webhooks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    secret: Mapped[str] = mapped_column(String(255), nullable=False)
    events: Mapped[List[str]] = mapped_column(JSON, default=lambda: ["conversation.created", "message.received"])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_delivery_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    last_delivery_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

class UsageRecord(Base):
    __tablename__ = "usage_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    period_date: Mapped[str] = mapped_column(String(10), index=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_messages: Mapped[int] = mapped_column(Integer, default=0)
    total_conversations: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="usage_records")
    __table_args__ = (UniqueConstraint('tenant_id', 'period_date', name='uq_tenant_period'),)

class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(50), default="info")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    link: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="notifications")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant", back_populates="audit_logs")


# ----------------- LAYER 2: AI PLATFORM & RAG MODELS -----------------

class AIAssistant(Base):
    __tablename__ = "ai_assistants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    personality_type: Mapped[str] = mapped_column(String(50), default="professional")
    
    model_name: Mapped[str] = mapped_column(String(100), default="gemini-1.5-flash")
    temperature: Mapped[float] = mapped_column(Float, default=0.3)
    top_p: Mapped[float] = mapped_column(Float, default=0.95)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=1024)
    
    system_instruction: Mapped[str] = mapped_column(Text, default="You are an enterprise AI assistant for customer support. Answer politely and accurately.")
    fallback_message: Mapped[str] = mapped_column(String(500), default="I am transferring you to a human agent.")
    
    safety_settings: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    auto_handover_keywords: Mapped[List[str]] = mapped_column(JSON, default=lambda: ["agent", "human", "representative", "support", "talk to human"])
    sentiment_threshold_for_handover: Mapped[float] = mapped_column(Float, default=-0.6)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="assistants")
    websites: Mapped[List["Website"]] = relationship("Website", back_populates="assistant")

class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), default="General")
    source_type: Mapped[str] = mapped_column(String(50), default="document")
    source_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="indexed")
    chunk_count: Mapped[int] = mapped_column(Integer, default=1)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="knowledge_bases")
    chunks: Mapped[List["KnowledgeChunk"]] = relationship("KnowledgeChunk", back_populates="knowledge_base", cascade="all, delete-orphan")

class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    
    embedding_json: Mapped[List[float]] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    knowledge_base: Mapped["KnowledgeBase"] = relationship("KnowledgeBase", back_populates="chunks")


# ----------------- LAYER 3: WEBSITES, CONTACTS, CHAT & INBOX -----------------

class Website(Base):
    __tablename__ = "websites"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    assistant_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("ai_assistants.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    widget_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    
    primary_color: Mapped[str] = mapped_column(String(32), default="#4F46E5")
    header_title: Mapped[str] = mapped_column(String(100), default="Live AI Support")
    welcome_message: Mapped[str] = mapped_column(String(500), default="Hello! How can we assist you today?")
    position: Mapped[str] = mapped_column(String(20), default="bottom-right")
    
    # E-Commerce & Widget Customization Configuration
    business_category: Mapped[str] = mapped_column(String(50), default="ecommerce")
    ecommerce_config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    branding_config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="websites")
    assistant: Mapped[Optional["AIAssistant"]] = relationship("AIAssistant", back_populates="websites")
    conversations: Mapped[List["Conversation"]] = relationship("Conversation", back_populates="website")
    orders: Mapped[List["Order"]] = relationship("Order", back_populates="website")

class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), index=True, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    custom_attributes: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="contacts")
    conversations: Mapped[List["Conversation"]] = relationship("Conversation", back_populates="contact")

class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    website_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("websites.id", ondelete="SET NULL"), nullable=True)
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    assigned_agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    visitor_session_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    visitor_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    visitor_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    visitor_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    
    status: Mapped[ConversationStatus] = mapped_column(Enum(ConversationStatus), default=ConversationStatus.AI_ACTIVE)
    priority: Mapped[ConversationPriority] = mapped_column(Enum(ConversationPriority), default=ConversationPriority.MEDIUM)
    department: Mapped[str] = mapped_column(String(100), default="Support")
    ai_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    
    last_sentiment_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_lead_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    lead_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    unread_count: Mapped[int] = mapped_column(Integer, default=0)

    # CSAT & Performance Metrics
    csat_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True) # 1 to 5 stars
    csat_feedback: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    first_response_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="conversations")
    website: Mapped[Optional["Website"]] = relationship("Website", back_populates="conversations")
    contact: Mapped[Optional["Contact"]] = relationship("Contact", back_populates="conversations")
    assigned_agent: Mapped[Optional["User"]] = relationship("User", back_populates="assigned_conversations")
    messages: Mapped[List["Message"]] = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    orders: Mapped[List["Order"]] = relationship("Order", back_populates="conversation")

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False)
    sender_type: Mapped[SenderType] = mapped_column(Enum(SenderType), nullable=False)
    sender_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    sender_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal_note: Mapped[bool] = mapped_column(Boolean, default=False)
    
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sources_cited: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")

class PricingPlan(Base):
    __tablename__ = "pricing_plans"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False) # e.g. 'starter', 'growth', 'enterprise', 'eid_special'
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    badge_text: Mapped[Optional[str]] = mapped_column(String(64), nullable=True) # e.g. 'MOST POPULAR', '50% OFF'

    monthly_price_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    annual_price_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    
    monthly_token_limit: Mapped[int] = mapped_column(Integer, default=500_000)
    max_agents: Mapped[int] = mapped_column(Integer, default=2)
    max_websites: Mapped[int] = mapped_column(Integer, default=1)
    max_knowledge_docs: Mapped[int] = mapped_column(Integer, default=10)
    monthly_conversation_limit: Mapped[int] = mapped_column(Integer, default=1000)

    features: Mapped[List[str]] = mapped_column(JSON, default=list)
    is_popular: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_custom_offer: Mapped[bool] = mapped_column(Boolean, default=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

class Coupon(Base):
    __tablename__ = "coupons"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False) # e.g. 'EID2026', 'STARTUP50'
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    discount_type: Mapped[str] = mapped_column(String(32), default="percentage") # 'percentage' or 'fixed_amount'
    discount_value: Mapped[float] = mapped_column(Float, nullable=False) # e.g. 20.0 (20%) or 1000.0 (৳1,000)
    
    min_purchase_amount_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    max_discount_amount_bdt: Mapped[Optional[float]] = mapped_column(Float, nullable=True) # cap on percentage discount
    applicable_tiers: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True) # list of plan codes or None for all
    
    max_redemptions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True) # None = unlimited
    redeemed_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

class CouponRedemption(Base):
    __tablename__ = "coupon_redemptions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    coupon_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("coupons.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True)
    user_email: Mapped[str] = mapped_column(String(255), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(128), nullable=False)
    
    original_amount_bdt: Mapped[float] = mapped_column(Float, nullable=False)
    discount_applied_bdt: Mapped[float] = mapped_column(Float, nullable=False)
    final_paid_amount_bdt: Mapped[float] = mapped_column(Float, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    coupon: Mapped["Coupon"] = relationship("Coupon")

class PlatformSetting(Base):
    __tablename__ = "platform_settings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    value_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


# ----------------- LAYER 6: CONVERSATIONAL E-COMMERCE MODELS -----------------

class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(100), default="General")
    sku: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    unit_price: Mapped[float] = mapped_column(Float, default=0.0) # MSRP / Regular Price in BDT
    selling_price: Mapped[float] = mapped_column(Float, default=0.0) # Offer / Selling Price in BDT
    
    stock_quantity: Mapped[int] = mapped_column(Integer, default=100)
    stock_status: Mapped[str] = mapped_column(String(50), default="in_stock") # in_stock, out_of_stock, pre_order
    
    images: Mapped[List[str]] = mapped_column(JSON, default=list) # Array of image URLs
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    specifications: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict) # color, size, warranty, features
    tags: Mapped[List[str]] = mapped_column(JSON, default=list) # Multilingual search keywords & synonyms (e.g. ['smartwatch', 'watch', 'ঘড়ি'])
    
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False) # 1=highest, 0=no priority (sorted by created_at)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="products")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_number: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    website_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("websites.id", ondelete="SET NULL"), nullable=True)
    conversation_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_phone: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    customer_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    delivery_address: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_city: Mapped[str] = mapped_column(String(100), default="Dhaka")
    delivery_charge: Mapped[float] = mapped_column(Float, default=60.0)
    
    items_json: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list) # [{"product_id": "...", "title": "...", "price": 2490, "quantity": 1, "size": "L"}]
    subtotal_amount: Mapped[float] = mapped_column(Float, default=0.0)
    total_amount: Mapped[float] = mapped_column(Float, default=0.0) # subtotal + delivery_charge
    
    payment_method: Mapped[str] = mapped_column(String(50), default="cash_on_delivery") # cash_on_delivery, bkash
    payment_status: Mapped[str] = mapped_column(String(50), default="unpaid") # unpaid, paid, refunded
    bkash_trx_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    order_status: Mapped[str] = mapped_column(String(50), default="pending") # pending, confirmed, shipped, delivered, cancelled
    sms_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    tracking_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="orders")
    website: Mapped[Optional["Website"]] = relationship("Website", back_populates="orders")
    conversation: Mapped[Optional["Conversation"]] = relationship("Conversation", back_populates="orders")
