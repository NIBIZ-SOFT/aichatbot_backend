from typing import Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.models.all_models import PlatformSetting


class PublicPagesService:
    DEFAULT_PAGES: Dict[str, Dict[str, Any]] = {
        "about": {
            "slug": "about",
            "title": "About Jobab.chat — Next-Gen Conversational AI Infrastructure",
            "subtitle": "Pioneering enterprise AI for Bangladeshi commerce, healthcare, fintech, and omnichannel support desks.",
            "meta_title": "About Us — Jobab.chat | Enterprise AI Platform Bangladesh",
            "meta_description": "Discover Jobab.chat's mission, autonomous multilingual AI agents, multi-tenant database isolation, and native bKash commerce automation.",
            "last_updated": "September 2026",
            "badge": "ENTERPRISE AI PLATFORM",
            "content": """
## Who We Are
Jobab.chat is an enterprise-grade AI conversational automation platform purpose-built for the fast-evolving digital commerce, ERP, and customer helpline landscape in Bangladesh. We bridge the gap between complex Large Language Models (LLMs) and everyday commercial operations, enabling businesses to provide 24/7 instant, accurate, and human-like customer care in both Bengali and English.

---

## The Problem We Solve
Traditional support in Bangladesh relies heavily on manual social media teams, leading to delayed response times, lost orders during off-hours, and high staff turnover. Off-the-shelf global chatbot tools fail to understand colloquial Bangladeshi contexts, regional dialects, and direct mobile financial services like bKash.

Jobab.chat solves this with:
- **Bilingual & Colloquial Understanding:** Natural language processing trained on localized Bengali and Banglish nuances.
- **Automated bKash & EPS Billing:** Instant merchant checkouts, tokenized recurring billing, and prepaid wallet top-ups.
- **Omnichannel Integration:** A single unified inbox connecting website widgets, WhatsApp, Facebook Messenger, and custom APIs.
- **Seamless Human Handover:** When complex queries arise, the AI smoothly routes conversations to human agents with full context summaries.

---

## Enterprise Multi-Tenant Architecture
Security and data integrity are the bedrock of Jobab.chat. Our cloud infrastructure features:
1. **Isolated Tenant Workspaces:** Your customer conversations, products, orders, and knowledge base documents are strictly segregated.
2. **Zero Cross-Tenant Model Training:** Your proprietary business data and customer transcripts are never used to train global public models.
3. **99.9% Uptime Guarantee:** High-availability server clusters with automated failovers and low-latency response delivery.
4. **Bank-Grade Encryption:** TLS 1.3 in transit and AES-256 at rest across all databases.

---

## Our Vision
We envision a future where every business in Bangladesh—from emerging direct-to-consumer retailers to nationwide financial helplines—can deliver world-class, instantaneous customer delight without runaway staffing overheads.
"""
        },
        "privacy": {
            "slug": "privacy",
            "title": "Privacy Policy",
            "subtitle": "Transparent data protection, strict tenant isolation, and regulatory compliance standards.",
            "meta_title": "Privacy Policy — Jobab.chat Enterprise Data Protection",
            "meta_description": "Read Jobab.chat's comprehensive privacy policy, customer data encryption protocols, bKash financial privacy, and user rights.",
            "last_updated": "September 2026",
            "badge": "DATA PROTECTION & COMPLIANCE",
            "content": """
## 1. Introduction
At Jobab.chat ("we", "our", or "us"), we prioritize the privacy, confidentiality, and security of our business clients ("Tenants") and their end-user customers ("End Users"). This Privacy Policy explains how we collect, store, process, and safeguard information when you use the Jobab.chat platform, website, live chat widgets, and developer APIs.

---

## 2. Information We Collect
We collect information strictly necessary to provide our conversational AI and billing services:
- **Account & Profile Data:** Organization name, administrator email, contact details, and authentication credentials.
- **Customer Conversation Logs:** Chat transcripts submitted through website widgets or messaging integrations, utilized exclusively to generate AI responses and populate your team inbox.
- **Knowledge Base Materials:** Documents, FAQs, product catalogs, and policies uploaded by your team for Retrieval-Augmented Generation (RAG).
- **Billing & Transaction Data:** Transaction identifiers, invoice numbers, and payment status received from licensed gateways (bKash Direct Merchant and EPS Payment Gateway). **We do not store your bKash PIN or credit card numbers.**

---

## 3. Strict AI Confidentiality Guarantee
**We do not use your business documents or customer chat data to train public foundational AI models.**
All AI prompts and context retrievals are executed inside isolated private sessions. Your data remains strictly your intellectual property.

---

## 4. How We Protect Your Data
- **Multi-Tenant Logical Isolation:** Each tenant's data is partitioned using strict tenant ID tenancy filters and encrypted storage.
- **Encryption in Transit & Rest:** All communications are secured using SSL/TLS 1.3 encryption. Storage volumes are protected with AES-256 encryption.
- **Role-Based Access Control (RBAC):** Only authorized staff members within your organization have access to customer conversation transcripts.
- **Automated Audit Logging:** Every administrative action, contract change, and data export is permanently recorded in our security audit log.

---

## 5. Third-Party Integrations
Jobab.chat integrates with certified infrastructure partners:
- **Payment Gateways:** bKash Limited and EPS Payment Gateway for processing subscription and wallet recharges under Bangladesh Bank regulations.
- **LLM Infrastructure Providers:** Enterprise LLM endpoints operating under strict business data confidentiality agreements.

---

## 6. Data Retention & Deletion Rights
You retain full ownership of your data. You may at any time:
- Request a full JSON/CSV export of your conversations and contacts.
- Request permanent deletion of all stored transcripts, uploaded knowledge documents, and organization records upon subscription cancellation.

---

## 7. Contact Us Regarding Privacy
For inquiries regarding our data practices or to submit a data protection request, please contact:
- **Email:** privacy@jobab.chat / support@jobab.chat
- **Address:** Jobab.chat Headquarters, Dhaka, Bangladesh.
"""
        },
        "terms": {
            "slug": "terms",
            "title": "Terms and Conditions of Service",
            "subtitle": "Clear usage guidelines, subscription terms, AI token quotas, and service commitments.",
            "meta_title": "Terms of Service — Jobab.chat Commercial Agreement",
            "meta_description": "Review the Jobab.chat terms and conditions, subscription billing rules, AI token usage, refund policy, and 99.9% uptime SLA.",
            "last_updated": "September 2026",
            "badge": "LEGAL AGREEMENT",
            "content": """
## 1. Agreement to Terms
By creating an account, embedding our live chat widget, or subscribing to any Jobab.chat plan, you agree to be bound by these Terms of Service. If you do not agree to these terms, do not access or use the platform.

---

## 2. Platform Access & Account Responsibility
- **Authorized Representative:** You represent that you have the authority to bind your business organization to these terms.
- **Account Security:** You are responsible for safeguarding your administrator credentials and ensuring authorized access among your team seats.
- **Acceptable Use:** You agree not to use Jobab.chat to transmit unlawful, defamatory, fraudulent, or harmful materials, or to engage in unauthorized spam distribution.

---

## 3. Subscriptions, AI Tokens & Billing
- **Subscription Tiers:** We offer monthly and annual subscriptions (Starter, Growth, Enterprise) as well as Pay-As-You-Go prepaid wallet plans.
- **Token Quotas:** Each plan includes a designated monthly AI token allotment. If your token quota is exhausted, you may recharge your prepaid AI wallet or upgrade your plan.
- **Automated Billing:** Payments are processed in Bangladeshi Taka (BDT) via official bKash Merchant APIs and EPS Payment Gateway.
- **Taxes & Invoicing:** Automated VAT and tax-compliant digital invoices are generated and accessible within your organization billing desk.

---

## 4. Refund & Cancellation Policy
- **Subscription Cancellation:** You may cancel your subscription at any time via the Subscription tab in your dashboard. Access will continue until the end of your prepaid billing period.
- **Refund Eligibility:** Due to direct computational costs incurred with AI processing, subscription fees and consumed AI tokens are generally non-refundable. However, if a billing discrepancy or gateway double-charge occurs, our support team will issue a refund within 5–7 business days upon verification.

---

## 5. Service Level Agreement (SLA) & Uptime
- **99.9% Uptime Commitment:** We strive to maintain continuous platform availability, excluding scheduled maintenance announced at least 24 hours in advance.
- **Support Response SLAs:** Priority email and ticket support response times are determined by your subscribed plan tier (Starter: 24h SLA, Growth: 6h SLA, Enterprise: 1h dedicated SLA).

---

## 6. Limitation of Liability
Jobab.chat provides autonomous AI assistance based on your uploaded documentation and prompts. While our models are tuned for high accuracy, you are advised to maintain human oversight for critical business transactions and medical/legal advice. Jobab.chat shall not be liable for indirect or consequential damages arising from service interruptions.

---

## 7. Governing Law & Dispute Resolution
These Terms shall be governed by and construed in accordance with the laws of the People's Republic of Bangladesh. Any disputes shall be resolved through good-faith negotiation or arbitration in Dhaka, Bangladesh.
"""
        }
    }

    @classmethod
    async def get_all_pages(cls, db: AsyncSession) -> Dict[str, Any]:
        """
        Retrieves all public pages from PlatformSetting, merged with defaults.
        """
        stmt = select(PlatformSetting).where(PlatformSetting.key == "platform_public_pages")
        setting = (await db.execute(stmt)).scalars().first()

        if not setting or not setting.value_json:
            return dict(cls.DEFAULT_PAGES)

        merged = dict(cls.DEFAULT_PAGES)
        for k, v in setting.value_json.items():
            if k in merged:
                merged[k] = {**merged[k], **v}
            else:
                merged[k] = v
        return merged

    @classmethod
    async def get_page(cls, db: AsyncSession, slug: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a single public page by slug (e.g. 'about', 'privacy', 'terms').
        """
        slug = slug.strip().lower()
        if slug in ["privacy-policy", "privacy"]:
            slug = "privacy"
        elif slug in ["terms-and-conditions", "terms-of-service", "terms"]:
            slug = "terms"

        all_pages = await cls.get_all_pages(db)
        return all_pages.get(slug)

    @classmethod
    async def update_page(cls, db: AsyncSession, slug: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Updates a specific public page in PostgreSQL PlatformSetting table.
        """
        slug = slug.strip().lower()
        if slug in ["privacy-policy", "privacy"]:
            slug = "privacy"
        elif slug in ["terms-and-conditions", "terms-of-service", "terms"]:
            slug = "terms"

        stmt = select(PlatformSetting).where(PlatformSetting.key == "platform_public_pages")
        setting = (await db.execute(stmt)).scalars().first()

        current_pages = dict(cls.DEFAULT_PAGES)
        if setting and setting.value_json:
            for k, v in setting.value_json.items():
                if k in current_pages:
                    current_pages[k] = {**current_pages[k], **v}
                else:
                    current_pages[k] = v

        page_to_update = current_pages.get(slug, {
            "slug": slug,
            "title": data.get("title", slug.capitalize()),
            "subtitle": data.get("subtitle", ""),
            "meta_title": data.get("meta_title", ""),
            "meta_description": data.get("meta_description", ""),
            "last_updated": data.get("last_updated", "September 2026"),
            "badge": data.get("badge", "LEGAL"),
            "content": data.get("content", "")
        })

        page_to_update.update(data)
        page_to_update["slug"] = slug
        current_pages[slug] = page_to_update

        if not setting:
            setting = PlatformSetting(
                key="platform_public_pages",
                value_json=current_pages
            )
            db.add(setting)
        else:
            setting.value_json = dict(current_pages)
            flag_modified(setting, "value_json")
            setting.updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(setting)
        return page_to_update
