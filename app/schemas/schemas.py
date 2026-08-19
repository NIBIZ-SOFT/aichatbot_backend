import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, EmailStr
from app.models.all_models import (
    UserRole, SubscriptionTier, SubscriptionStatus,
    ConversationStatus, ConversationPriority, SenderType
)

# ---------------- Auth & Tenant ----------------
class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    tenant_name: str

class TenantProvisionRequest(BaseModel):
    organization_name: str
    admin_name: str
    admin_email: str
    password: str
    subscription_tier: SubscriptionTier = SubscriptionTier.STARTER
    billing_cycle: str = "monthly"

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant_id: Optional[uuid.UUID] = None
    user_id: uuid.UUID
    role: UserRole
    full_name: str

class UserOut(BaseModel):
    id: uuid.UUID
    tenant_id: Optional[uuid.UUID]
    email: str
    full_name: str
    role: UserRole
    department: Optional[str]
    is_active: bool
    is_online: bool
    avatar_url: Optional[str]
    enabled_modules: Optional[Dict[str, bool]] = None
    tenant_name: Optional[str] = None
    created_at: datetime
    class Config:
        from_attributes = True

class TeamMemberCreate(BaseModel):
    full_name: str
    email: str
    password: str = "DemoPass123!"
    role: UserRole = UserRole.SUPPORT_AGENT
    department: Optional[str] = "Customer Support"

class TeamMemberUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    department: Optional[str] = None
    is_active: Optional[bool] = None

class TeamSeatsSummary(BaseModel):
    total_members: int
    max_seats: int
    seats_available: int
    is_limit_reached: bool
    members: List[UserOut]

class TenantOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    custom_domain: Optional[str] = None
    whitelabel_enabled: bool = False
    branding_config: Dict[str, Any] = {}
    created_at: datetime
    class Config:
        from_attributes = True

class TenantSettingsUpdate(BaseModel):
    name: Optional[str] = None
    custom_domain: Optional[str] = None
    branding_config: Optional[Dict[str, Any]] = None
    whitelabel_enabled: Optional[bool] = None

TenantUpdate = TenantSettingsUpdate

# ---------------- AI Assistants ----------------
class AIAssistantCreate(BaseModel):
    name: str
    description: Optional[str] = None
    personality_type: str = "professional"
    model_name: str = "gemini-1.5-flash"
    temperature: float = 0.3
    top_p: float = 0.95
    max_output_tokens: int = 1024
    system_instruction: str
    fallback_message: str = "I will transfer you to a human support agent."
    auto_handover_keywords: List[str] = ["human", "agent", "representative", "help"]
    safety_settings: Optional[Dict[str, Any]] = None

class AIAssistantUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    personality_type: Optional[str] = None
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_output_tokens: Optional[int] = None
    system_instruction: Optional[str] = None
    fallback_message: Optional[str] = None
    auto_handover_keywords: Optional[List[str]] = None
    safety_settings: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class AIAssistantOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: Optional[str]
    personality_type: str
    model_name: str
    temperature: float
    top_p: float
    max_output_tokens: int
    system_instruction: str
    fallback_message: str
    auto_handover_keywords: List[str]
    safety_settings: Optional[Dict[str, Any]] = None
    is_active: bool
    created_at: datetime
    class Config:
        from_attributes = True

# ---------------- Knowledge & RAG ----------------
class KnowledgeBaseCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: str = "General"
    source_type: str = "manual"
    content_raw: Optional[str] = None

class KnowledgeIngestText(BaseModel):
    title: str
    content: str
    category: str = "General"
    source_type: str = "markdown_doc"
    source_url: Optional[str] = None

class FAQItem(BaseModel):
    question: str
    answer: str

class KnowledgeIngestFAQ(BaseModel):
    title: str
    category: str = "FAQ"
    faq_items: List[FAQItem]

class KnowledgeSearchSandbox(BaseModel):
    query: str
    limit: Optional[int] = 4

class TestChatPayload(BaseModel):
    message: str
    assistant_id: Optional[uuid.UUID] = None

class KnowledgeSearchResult(BaseModel):
    source: str
    category: str
    content: str
    similarity: float

class KnowledgeBaseOut(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str]
    category: str
    source_type: str
    source_url: Optional[str]
    status: str
    chunk_count: int
    created_at: datetime
    class Config:
        from_attributes = True

# ---------------- Website & Widget ----------------
class WebsiteCreate(BaseModel):
    assistant_id: Optional[uuid.UUID] = None
    name: str
    domain: str
    primary_color: str = "#4F46E5"
    header_title: str = "Live AI Support"
    welcome_message: str = "Hi! How can I help you today?"
    position: str = "bottom-right"
    business_category: str = "ecommerce"
    ecommerce_config: Optional[Dict[str, Any]] = None
    branding_config: Optional[Dict[str, Any]] = None

class WebsiteOut(BaseModel):
    id: uuid.UUID
    assistant_id: Optional[uuid.UUID]
    name: str
    domain: str
    widget_key: str
    primary_color: str
    header_title: str
    welcome_message: str
    position: str
    business_category: Optional[str] = "ecommerce"
    ecommerce_config: Optional[Dict[str, Any]] = None
    branding_config: Optional[Dict[str, Any]] = None
    is_active: bool
    created_at: datetime
    class Config:
        from_attributes = True

# ---------------- Contacts & CRM ----------------
class ContactCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    tags: List[str] = []

class ContactOut(BaseModel):
    id: uuid.UUID
    name: str
    email: Optional[str]
    phone: Optional[str]
    company: Optional[str]
    tags: List[str]
    created_at: datetime
    class Config:
        from_attributes = True

# ---------------- Live Chat & Inbox ----------------
class ConversationOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    website_id: Optional[uuid.UUID]
    contact_id: Optional[uuid.UUID]
    visitor_session_id: str
    visitor_name: Optional[str]
    visitor_email: Optional[str]
    status: ConversationStatus
    priority: ConversationPriority
    department: str
    ai_paused: bool
    last_sentiment_score: Optional[float]
    is_lead_detected: bool
    lead_data: Dict[str, Any]
    ai_summary: Optional[str]
    tags: List[str]
    unread_count: int
    last_message_at: datetime
    created_at: datetime
    class Config:
        from_attributes = True

class ConversationUpdate(BaseModel):
    status: Optional[ConversationStatus] = None
    priority: Optional[ConversationPriority] = None
    department: Optional[str] = None
    assigned_agent_id: Optional[uuid.UUID] = None
    ai_paused: Optional[bool] = None
    tags: Optional[List[str]] = None

class MessageCreate(BaseModel):
    content: str
    is_internal_note: bool = False

class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_type: SenderType
    sender_id: Optional[str]
    sender_name: Optional[str]
    content: str
    is_internal_note: bool
    prompt_tokens: int
    completion_tokens: int
    latency_ms: Optional[int]
    sources_cited: List[Dict[str, Any]]
    created_at: datetime
    class Config:
        from_attributes = True

class WidgetInitSession(BaseModel):
    widget_key: str
    visitor_session_id: Optional[str] = None
    visitor_name: Optional[str] = None
    visitor_email: Optional[str] = None
    visitor_phone: Optional[str] = None
    current_url: Optional[str] = None
    user_agent: Optional[str] = None
    page_context: Optional[Dict[str, Any]] = None

class WidgetMessageSend(BaseModel):
    widget_key: str
    visitor_session_id: str
    content: str
    page_context: Optional[Dict[str, Any]] = None

# ---------------- Operations, Subscriptions, Usage ----------------
class SubscriptionOut(BaseModel):
    id: uuid.UUID
    tier: SubscriptionTier
    status: SubscriptionStatus
    monthly_token_limit: int
    monthly_conversation_limit: int = 10000
    max_agents: int = 25
    max_websites: int = 10
    max_knowledge_docs: int = 500
    current_period_start: datetime
    current_period_end: datetime
    class Config:
        from_attributes = True

class PlanChangeRequest(BaseModel):
    tier: str
    billing_cycle: Optional[str] = "monthly"
    payment_method: Optional[str] = "bKash Direct Merchant"

class SubscriptionDetailsOut(BaseModel):
    id: uuid.UUID
    tenant_name: str
    tier: str
    plan_code: Optional[str] = None
    status: str
    price_bdt: float
    billing_cycle: str
    monthly_token_limit: int
    used_tokens: int
    usage_percent: float
    max_agents: int
    current_agents_count: int
    max_websites: int
    current_websites_count: int
    current_period_start: datetime
    current_period_end: datetime
    payment_method: str
    whitelabel_enabled: bool
    custom_cname_enabled: bool

class InvoiceItemOut(BaseModel):
    id: str
    invoice_number: str
    date: datetime
    plan_name: str
    billing_cycle: str
    amount_bdt: float
    payment_method: str
    status: str
    receipt_url: str

class UsageRecordOut(BaseModel):
    id: uuid.UUID
    period_date: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    total_messages: int
    total_conversations: int
    estimated_cost_usd: float
    class Config:
        from_attributes = True

class ModelUsageItem(BaseModel):
    model: str
    tokens: int
    cost_usd: float
    percentage: float

class WebsiteUsageItem(BaseModel):
    website_name: str
    domain: str
    tokens: int
    conversations: int
    cost_usd: float

class DailyUsageItem(BaseModel):
    date: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float

class UsageSummaryOut(BaseModel):
    billing_period: str
    tier_name: str
    total_tokens: int
    monthly_token_limit: int
    quota_used_percentage: float
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    total_messages: int
    total_conversations: int
    resets_at: str
    models_breakdown: List[ModelUsageItem]
    websites_breakdown: List[WebsiteUsageItem]
    daily_history: List[DailyUsageItem]

class ApiKeyCreate(BaseModel):
    name: str
    scopes: List[str] = ["chat:read", "chat:write", "rag:search"]

class ApiKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: List[str]
    is_active: bool
    created_at: datetime
    class Config:
        from_attributes = True

class ApiKeyCreatedResponse(BaseModel):
    id: uuid.UUID
    name: str
    api_key: str
    key_prefix: str
    scopes: List[str]
    created_at: datetime

class WebhookCreate(BaseModel):
    url: str
    events: List[str] = ["conversation.created", "message.received"]

class WebhookOut(BaseModel):
    id: uuid.UUID
    url: str
    events: List[str]
    is_active: bool
    last_delivery_status: Optional[str]
    created_at: datetime
    class Config:
        from_attributes = True

class NotificationOut(BaseModel):
    id: uuid.UUID
    title: str
    message: str
    type: str
    is_read: bool
    link: Optional[str]
    created_at: datetime
    class Config:
        from_attributes = True

class AuditLogOut(BaseModel):
    id: uuid.UUID
    action: str
    resource_type: str
    resource_id: Optional[str]
    ip_address: Optional[str]
    created_at: datetime
    class Config:
        from_attributes = True

class DashboardStatsOut(BaseModel):
    total_conversations: int
    ai_resolved_count: int
    human_resolved_count: int
    pending_count: int
    active_visitors: int
    total_tokens_used: int
    token_limit: int
    usage_percentage: float
    total_contacts: int
    total_websites: int

class AnalyticsTrendPoint(BaseModel):
    date: str
    conversations: int
    ai_responses: int
    human_responses: int
    tokens: int

# ----------------- E-COMMERCE & CONVERSATIONAL COMMERCE SCHEMAS -----------------

class ProductCreate(BaseModel):
    title: str
    category: str = "General"
    sku: Optional[str] = None
    unit_price: float = 0.0
    selling_price: float = 0.0
    stock_quantity: int = 100
    stock_status: str = "in_stock" # in_stock, out_of_stock, pre_order
    images: List[str] = []
    description: Optional[str] = None
    specifications: Optional[Dict[str, Any]] = None
    is_active: bool = True

class ProductUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    sku: Optional[str] = None
    unit_price: Optional[float] = None
    selling_price: Optional[float] = None
    stock_quantity: Optional[int] = None
    stock_status: Optional[str] = None
    images: Optional[List[str]] = None
    description: Optional[str] = None
    specifications: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class ProductOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    title: str
    slug: str
    category: str
    sku: Optional[str]
    unit_price: float
    selling_price: float
    stock_quantity: int
    stock_status: str
    images: List[str]
    description: Optional[str]
    specifications: Dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True

class OrderItemIn(BaseModel):
    product_id: str
    title: str
    price: float
    quantity: int = 1
    selected_size: Optional[str] = None
    selected_color: Optional[str] = None
    image_url: Optional[str] = None

class OrderCreate(BaseModel):
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    delivery_address: str
    delivery_city: str = "Dhaka"
    items: List[OrderItemIn]
    payment_method: str = "cash_on_delivery" # cash_on_delivery, bkash
    website_id: Optional[uuid.UUID] = None
    conversation_id: Optional[uuid.UUID] = None

class PublicWidgetOrderCreate(BaseModel):
    widget_key: str
    visitor_session_id: str
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    delivery_address: str
    delivery_city: str = "Dhaka"
    items: List[OrderItemIn]
    payment_method: str = "cash_on_delivery" # cash_on_delivery, bkash

class OrderStatusUpdate(BaseModel):
    order_status: str # pending, confirmed, shipped, delivered, cancelled
    payment_status: Optional[str] = None # unpaid, paid, refunded
    tracking_notes: Optional[str] = None
    send_sms_notification: bool = True

class OrderOut(BaseModel):
    id: uuid.UUID
    order_number: str
    tenant_id: uuid.UUID
    website_id: Optional[uuid.UUID]
    conversation_id: Optional[uuid.UUID]
    customer_name: str
    customer_phone: str
    customer_email: Optional[str]
    delivery_address: str
    delivery_city: str
    delivery_charge: float
    items_json: List[Dict[str, Any]]
    subtotal_amount: float
    total_amount: float
    payment_method: str
    payment_status: str
    bkash_trx_id: Optional[str]
    order_status: str
    sms_sent: bool
    tracking_notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True

class EcommerceSettingsOut(BaseModel):
    business_category: str = "ecommerce"
    cod_enabled: bool = True
    bkash_enabled: bool = False
    bkash_is_sandbox: bool = True
    bkash_base_url: Optional[str] = "https://tokenized.sandbox.bka.sh/v1.2.0-beta"
    bkash_app_key_masked: Optional[str] = None
    bkash_username_masked: Optional[str] = None
    delivery_charge_inside_dhaka: float = 60.0
    delivery_charge_outside_dhaka: float = 120.0
    sms_notifications_enabled: bool = True
    sms_provider: str = "smsmatrix"
    sms_sender_id_masked: Optional[str] = None
    sms_order_template: Optional[str] = None

class EcommerceSettingsUpdate(BaseModel):
    business_category: Optional[str] = None
    cod_enabled: Optional[bool] = None
    bkash_enabled: Optional[bool] = None
    bkash_is_sandbox: Optional[bool] = None
    bkash_base_url: Optional[str] = None
    bkash_app_key: Optional[str] = None
    bkash_app_secret: Optional[str] = None
    bkash_username: Optional[str] = None
    bkash_password: Optional[str] = None
    delivery_charge_inside_dhaka: Optional[float] = None
    delivery_charge_outside_dhaka: Optional[float] = None
    sms_notifications_enabled: Optional[bool] = None
    sms_provider: Optional[str] = None
    sms_api_key: Optional[str] = None
    sms_sender_id: Optional[str] = None
class SwitchOrderCOD(BaseModel):
    widget_key: str
    visitor_session_id: str
    order_number: str

class RetryBkashPayment(BaseModel):
    widget_key: str
    visitor_session_id: str
    order_number: str
