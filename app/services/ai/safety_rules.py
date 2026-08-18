import re
from typing import Dict, Any, List, Tuple

class AISafetyAndRulesEngine:
    """
    Evaluates customer intent, sentiment, lead detection, and human handover triggers.
    """

    HANDOVER_TRIGGERS = [
        "speak to human", "talk to agent", "real person", "representative",
        "customer service", "help me human", "transfer", "complaint", "manager"
    ]

    EMAIL_REGEX = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    PHONE_REGEX = r'(\+?[0-9]{1,3}[-.\s]?)?(\(?[0-9]{2,4}\)?[-.\s]?)?[0-9]{3,4}[-.\s]?[0-9]{3,4}'

    @classmethod
    def check_human_handover(cls, user_message: str, custom_keywords: List[str] = None) -> bool:
        msg_lower = user_message.lower()
        triggers = cls.HANDOVER_TRIGGERS + (custom_keywords or [])
        return any(trigger in msg_lower for trigger in triggers)

    @classmethod
    def detect_lead(cls, user_message: str) -> Dict[str, Any]:
        """Extracts email and phone numbers automatically from chat messages."""
        emails = re.findall(cls.EMAIL_REGEX, user_message)
        phones = re.findall(cls.PHONE_REGEX, user_message)
        
        has_lead = len(emails) > 0 or len(phones) > 0
        return {
            "is_lead": has_lead,
            "emails": emails,
            "phones": [p[0] if isinstance(p, tuple) else p for p in phones if p]
        }

    @classmethod
    def analyze_sentiment(cls, user_message: str) -> float:
        """Basic sentiment scoring (-1.0 to +1.0)."""
        positive_words = ["great", "good", "awesome", "thanks", "helpful", "love", "perfect", "excellent"]
        negative_words = ["bad", "terrible", "worst", "angry", "broken", "useless", "hate", "fraud", "scam"]
        
    COMMON_OFF_TOPIC_PATTERNS = [
        r'\b(kobita|kobita bolo|poem|poetry|rhyme|sonnet|shonnet)\b',
        r'\b(python|javascript|c\+\+|java|html|css|sql|write code|coding|script|debug code)\b',
        r'\b(joke|koutuk|funny joke|hasir golpo|funny story)\b',
        r'\b(homework|essay|assignment|math problem|calculate equation|solve math)\b',
        r'\b(politics|election|vote|minister|political|bnp|awami|jammat)\b',
        r'\b(who is elon musk|who is einstein|who is president|capital of)\b',
        r'\b(recipe|ranna|biryani recipe|cooking recipe)\b'
    ]

    @classmethod
    def pre_flight_off_topic_check(cls, user_message: str, guardrails_cfg: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Ultra-Fast Zero-Token Pre-Flight Guardrail Interceptor.
        Checks if customer query violates restricted topics BEFORE calling RAG or Gemini.
        Returns (is_off_topic, reason).
        """
        if not guardrails_cfg or not guardrails_cfg.get("enabled", False):
            return False, ""

        msg_lower = user_message.lower().strip()
        restricted_topics = guardrails_cfg.get("restricted_topics", [])

        # 1. Check custom tenant restricted topic keywords
        for topic in restricted_topics:
            t_clean = topic.strip().lower()
            if t_clean and len(t_clean) > 2 and t_clean in msg_lower:
                return True, f"Matched restricted topic: {topic}"

        # 2. Check standard common off-topic regex patterns
        for pattern in cls.COMMON_OFF_TOPIC_PATTERNS:
            if re.search(pattern, msg_lower, re.IGNORECASE):
                return True, "Matched common off-topic pattern"

        return False, ""

    @classmethod
    def build_guarded_prompt(
        cls,
        raw_system_prompt: str,
        company_name: str = "Our Business",
        visitor_name: str = "Valued Customer",
        department: str = "Customer Support",
        current_date: str = "",
        safety_settings: Dict[str, Any] = None
    ) -> Tuple[str, bool, Dict[str, Any]]:
        """
        Substitutes dynamic template variables and injects strict AI Guardrail instructions
        based on tenant configuration.
        """
        safety_cfg = safety_settings or {}
        guardrails_cfg = safety_cfg.get("guardrails", {}) if isinstance(safety_cfg, dict) else {}
        is_guardrails_enabled = guardrails_cfg.get("enabled", False)

        guardrail_prompt_block = ""
        if is_guardrails_enabled:
            allowed_topics = guardrails_cfg.get("allowed_topics", [])
            restricted_topics = guardrails_cfg.get("restricted_topics", [])
            custom_warning = guardrails_cfg.get(
                "warning_message",
                f"I specialize in assisting with {company_name}'s products, pricing, orders, and services. How can I help you today?"
            )

            allowed_str = ", ".join(allowed_topics) if allowed_topics else "Product specifications, pricing, ordering, delivery, and store policies"
            restricted_str = ", ".join(restricted_topics) if restricted_topics else "General knowledge, poems, poetry, songs, coding, politics, homework, competitor comparisons, and unrelated topics"

            guardrail_prompt_block = f"""
### STRICT BUSINESS SCOPE & GUARDRAIL RULES:
You are an AI assistant exclusively serving {company_name}.
- PERMITTED TOPICS: {allowed_str}.
- STRICTLY FORBIDDEN / OFF-TOPIC: {restricted_str}.

CRITICAL INSTRUCTION:
If the user's message is OFF-TOPIC or asks about anything outside the permitted topics (e.g. poems, poetry, storytelling, general coding, math, world history, politics, casual unrelated chit-chat, personal opinions):
You MUST prefix your reply with `[OFF_TOPIC_VIOLATION]` followed immediately by:
"{custom_warning}"
Do NOT answer the off-topic question.
"""

        rendered = (
            (raw_system_prompt or "You are an enterprise AI assistant.")
            .replace("{{visitor_name}}", visitor_name)
            .replace("{{customer_name}}", visitor_name)
            .replace("{{company_name}}", company_name)
            .replace("{{organization_name}}", company_name)
            .replace("{{department}}", department)
            .replace("{{current_date}}", current_date)
        )
        if guardrail_prompt_block:
            rendered += "\n\n" + guardrail_prompt_block

        return rendered, is_guardrails_enabled, guardrails_cfg

    @classmethod
    def evaluate_guardrail_response(
        cls,
        ai_reply_text: str,
        guardrails_cfg: Dict[str, Any],
        current_strikes: int = 0
    ) -> Dict[str, Any]:
        """
        Evaluates AI reply for off-topic tokens, calculates multi-strike thresholds,
        and determines if AI should auto-pause.
        """
        is_violation = "[OFF_TOPIC_VIOLATION]" in ai_reply_text
        cleaned_text = ai_reply_text.replace("[OFF_TOPIC_VIOLATION]", "").strip()

        if not is_violation:
            return {
                "text": cleaned_text,
                "is_off_topic": False,
                "new_strikes": 0,
                "should_pause": False,
                "is_handover": False
            }

        new_strikes = current_strikes + 1
        max_strikes = int(guardrails_cfg.get("max_off_topic_strikes", 2))
        auto_pause = guardrails_cfg.get("auto_pause_on_breach", True)
        handover_msg = guardrails_cfg.get(
            "handover_message",
            "This inquiry appears to be outside our automated support scope. I am now pausing automated AI and transferring your request to our customer care team."
        )

        if new_strikes >= max_strikes and auto_pause:
            return {
                "text": handover_msg,
                "is_off_topic": True,
                "new_strikes": new_strikes,
                "should_pause": True,
                "is_handover": True
            }

        return {
            "text": cleaned_text,
            "is_off_topic": True,
            "new_strikes": new_strikes,
            "should_pause": False,
            "is_handover": False
        }
