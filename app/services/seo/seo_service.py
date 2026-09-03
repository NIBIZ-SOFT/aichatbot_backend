from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from sqlalchemy.orm.attributes import flag_modified

from app.models.all_models import PlatformSetting


class SeoService:
    DEFAULT_SEO_CONFIG: Dict[str, Any] = {
        # Core Search Metadata
        "meta_title": "Jobab Chat — AI-Powered Customer Support & Multilingual Sales Automation",
        "meta_description": "Transform customer support with Jobab Chat. 24/7 bilingual AI assistant in Bengali & English, live human inbox handover, bKash automated orders & isolated database architecture.",
        "meta_keywords": "ai chatbot bangladesh, customer service ai, bkash chatbot, e-commerce automation, bengali ai assistant, live chat widget, enterprise support ai, jobab chat",
        "canonical_url": "https://jobab.chat",
        "author": "Jobab Chat Enterprise",
        "robots": "index, follow",
        
        # Open Graph (Social Sharing - Facebook, LinkedIn, WhatsApp)
        "og_title": "Jobab Chat — Intelligent Bilingual Customer Support & Sales Automation",
        "og_description": "24/7 AI chatbot for Bangladeshi businesses with direct bKash integration, live human handover, and instant website widget embed.",
        "og_image_url": "https://jobab.chat/og-banner.png",
        "og_type": "website",
        "og_site_name": "Jobab Chat",
        "og_locale": "en_US",
        
        # Twitter / X Card
        "twitter_card": "summary_large_image",
        "twitter_title": "Jobab Chat — 24/7 AI Customer Support & Sales Automation",
        "twitter_description": "Automate customer conversations in Bengali & English with isolated enterprise AI.",
        "twitter_image_url": "https://jobab.chat/twitter-banner.png",
        "twitter_creator": "@jobabchat",
        
        # Search Engine Verification
        "google_site_verification": "",
        "bing_site_verification": "",
        
        # Analytics & Pixels
        "google_analytics_id": "",
        "google_tag_manager_id": "",
        "facebook_pixel_id": "",
        
        # Schema.org Structured Data
        "schema_org_name": "Jobab Chat",
        "schema_org_url": "https://jobab.chat",
        "schema_org_logo": "https://jobab.chat/logo.png",
        "schema_application_category": "BusinessApplication",
        "schema_price_currency": "BDT",
        "schema_price_min": 4990.0,
        "schema_rating_value": 4.9,
        "schema_review_count": 128
    }

    @classmethod
    async def get_seo_metadata(cls, db: AsyncSession) -> Dict[str, Any]:
        """
        Retrieves public platform SEO and metadata configuration from PostgreSQL.
        Merges stored values over default config.
        """
        stmt = select(PlatformSetting).where(PlatformSetting.key == "platform_seo_metadata")
        setting = (await db.execute(stmt)).scalars().first()
        
        if not setting or not setting.value_json:
            return dict(cls.DEFAULT_SEO_CONFIG)
            
        merged = {**cls.DEFAULT_SEO_CONFIG, **setting.value_json}
        return merged

    @classmethod
    async def update_seo_metadata(cls, db: AsyncSession, new_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Updates platform SEO and metadata configuration in PostgreSQL.
        """
        stmt = select(PlatformSetting).where(PlatformSetting.key == "platform_seo_metadata")
        setting = (await db.execute(stmt)).scalars().first()
        
        if not setting:
            setting = PlatformSetting(
                key="platform_seo_metadata",
                value_json=dict(new_data)
            )
            db.add(setting)
        else:
            current = dict(setting.value_json or {})
            current.update(new_data)
            setting.value_json = dict(current)
            flag_modified(setting, "value_json")
            setting.updated_at = datetime.now(timezone.utc)
            
        await db.commit()
        await db.refresh(setting)
        return setting.value_json
