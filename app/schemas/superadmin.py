import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

class ModuleConfigPayload(BaseModel):
    modules: Dict[str, bool] = Field(
        description="Dictionary of module keys and their boolean enabled state"
    )

class ModuleConfigResponse(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str
    tenant_slug: str
    enabled_modules: Dict[str, bool]
    active_module_count: int
    total_available_modules: int

class TenantListItemOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    owner_name: str
    owner_email: str
    subscription_tier: str
    subscription_status: str
    monthly_token_limit: int
    used_tokens: int
    usage_percent: float
    total_agents: int
    total_websites: int
    enabled_modules: Dict[str, bool]
    created_at: datetime
    custom_domain: Optional[str] = None

class TierRevenueItem(BaseModel):
    tier: str
    price_bdt: float
    active_count: int
    total_mrr_bdt: float

class BillingTransactionItem(BaseModel):
    id: str
    tenant_name: str
    tier: str
    amount_bdt: float
    date: datetime
    payment_method: str
    status: str
    invoice_number: str

class RevenueBreakdownOut(BaseModel):
    total_mrr_bdt: float
    total_arr_bdt: float
    total_subscribers: int
    tier_breakdown: List[TierRevenueItem]
    recent_transactions: List[BillingTransactionItem]

class InfrastructureStatusOut(BaseModel):
    master_ai_model: str
    ai_engine_status: str
    gemini_api_configured: bool
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_knowledge_chunks: int
    average_ai_latency_ms: int
    rate_limit_rpm_per_tenant: int
    platform_uptime_percent: float

class AISettingsPayload(BaseModel):
    api_key: Optional[str] = None
    ai_base_url: Optional[str] = "https://generativelanguage.googleapis.com/v1beta/openai/"
    master_model: str = "gemini-2.5-flash"
    fallback_model: str = "gemini-1.5-flash"
    embedding_model: str = "text-embedding-004"
    temperature: float = 0.3
    max_tokens: int = 2048
    rate_limit_rpm: int = 120
    system_prompt_prefix: Optional[str] = "You are an enterprise AI customer support specialist."

class AISettingsOut(BaseModel):
    api_key: str
    api_key_masked: str
    ai_base_url: str
    master_model: str
    fallback_model: str
    embedding_model: str
    temperature: float
    max_tokens: int
    rate_limit_rpm: int
    system_prompt_prefix: str
    status: str
    available_models: List[str]

class BkashSettingsPayload(BaseModel):
    is_sandbox: bool
    base_url: str
    app_key: str
    app_secret: str
    username: str
    password: str
    merchant_number: Optional[str] = "01837586105"

class BkashSettingsOut(BaseModel):
    is_sandbox: bool
    base_url: str
    app_key: str
    app_secret: str
    username: str
    password: str
    merchant_number: str
    status: str

class BkashTestConnectionResponse(BaseModel):
    status: str
    latency_ms: int
    message: str
    token_preview: str

class PricingPlanPayload(BaseModel):
    code: str
    name: str
    description: str
    badge_text: Optional[str] = None
    monthly_price_bdt: float
    annual_price_bdt: float
    monthly_token_limit: int
    max_agents: int
    max_websites: int
    max_knowledge_docs: int = 50
    monthly_conversation_limit: int = 1000
    features: List[str] = Field(default_factory=list)
    is_popular: bool = False
    is_active: bool = True
    is_custom_offer: bool = False
    display_order: int = 0
    valid_until: Optional[datetime] = None

class PricingPlanOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str
    badge_text: Optional[str] = None
    monthly_price_bdt: float
    annual_price_bdt: float
    monthly_token_limit: int
    max_agents: int
    max_websites: int
    max_knowledge_docs: int
    monthly_conversation_limit: int
    features: List[str]
    is_popular: bool
    is_active: bool
    is_custom_offer: bool
    display_order: int
    valid_until: Optional[datetime] = None
    created_at: datetime

class CouponPayload(BaseModel):
    code: str
    description: str
    discount_type: str = "percentage"  # "percentage" or "fixed_amount"
    discount_value: float
    min_purchase_amount_bdt: float = 0.0
    max_discount_amount_bdt: Optional[float] = None
    applicable_tiers: Optional[List[str]] = None
    max_redemptions: Optional[int] = None
    is_active: bool = True
    valid_until: Optional[datetime] = None

class CouponOut(BaseModel):
    id: uuid.UUID
    code: str
    description: str
    discount_type: str
    discount_value: float
    min_purchase_amount_bdt: float
    max_discount_amount_bdt: Optional[float] = None
    applicable_tiers: Optional[List[str]] = None
    max_redemptions: Optional[int] = None
    redeemed_count: int
    is_active: bool
    valid_from: datetime
    valid_until: Optional[datetime] = None
    created_at: datetime


