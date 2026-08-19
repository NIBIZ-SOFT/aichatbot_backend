import httpx
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class SMSService:
    """
    SOLID Pluggable SMS Gateway Dispatcher supporting:
    - SMSMatrix Developer API (https://smsmatrix.nibizhost.com/api/v1/sms/send) [Recommended]
    - Greenweb BD (https://api.greenweb.com.bd/api.php)
    - SSL Wireless (https://smsplus.sslwireless.com/api/v3/send-sms)
    - BulkSMS BD (http://bulksmsbd.net/api/smsapi)
    - Mock / Development Gateway
    """

    @classmethod
    def render_template(cls, template: str, context: Dict[str, Any]) -> str:
        """
        Renders template variables e.g. {{customer_name}}, {{order_id}}, {{total_amount}}, {{store_name}}
        """
        rendered = template
        for k, v in context.items():
            rendered = rendered.replace(f"{{{{{k}}}}}", str(v))
        return rendered

    @classmethod
    async def send_order_sms(
        cls,
        phone_number: str,
        message_text: str,
        sms_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Sends SMS to customer / merchant using the tenant's configured SMS gateway.
        """
        config = sms_config or {}
        is_enabled = config.get("enabled", True)
        if not is_enabled:
            return {"status": "skipped", "reason": "SMS notifications disabled in settings"}

        provider = config.get("provider", "smsmatrix").lower()
        api_key = config.get("api_key", "")
        sender_id = config.get("sender_id", "")

        # Format Bangladeshi Phone Number (Ensure standard 01XXXXXXXXX)
        clean_phone = phone_number.strip().replace(" ", "").replace("-", "")
        if clean_phone.startswith("+88"):
            clean_phone = clean_phone[3:]
        elif clean_phone.startswith("88"):
            clean_phone = clean_phone[2:]
        if not clean_phone.startswith("0") and len(clean_phone) == 10:
            clean_phone = f"0{clean_phone}"

        # If no live API key is configured or in test mode, mock the dispatch cleanly
        if not api_key or api_key.startswith("mock_") or api_key == "demo_api_key":
            logger.info(f"[MOCK_SMS_GATEWAY] Dispatched SMS via {provider} to {clean_phone}: '{message_text}'")
            return {
                "status": "delivered_mock",
                "phone": clean_phone,
                "provider": provider,
                "message": message_text
            }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # 1. SMSMatrix Developer API (Recommended)
                if provider in ["smsmatrix", "sms_matrix", "nibiz_sms"]:
                    url = "https://smsmatrix.nibizhost.com/api/v1/sms/send"
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "recipient": clean_phone,
                        "message": message_text
                    }
                    res = await client.post(url, json=payload, headers=headers)
                    try:
                        res_json = res.json()
                    except Exception:
                        res_json = {"raw_text": res.text}

                    if res.status_code == 200 and res_json.get("status") == "success":
                        logger.info(f"[SMSMatrix] SMS delivered to {clean_phone}. Balance remaining: {res_json.get('remaining_balance')}")
                        return {
                            "status": "sent",
                            "provider": "smsmatrix",
                            "phone": clean_phone,
                            "remaining_balance": res_json.get("remaining_balance"),
                            "details": res_json
                        }
                    else:
                        logger.warning(f"[SMSMatrix] Error sending SMS: {res_json}")
                        return {
                            "status": "failed",
                            "provider": "smsmatrix",
                            "phone": clean_phone,
                            "error": res_json.get("message", "Unknown SMSMatrix error"),
                            "http_status": res.status_code
                        }

                # 2. Greenweb BD
                elif provider == "greenweb":
                    url = "https://api.greenweb.com.bd/api.php"
                    params = {
                        "token": api_key,
                        "to": clean_phone,
                        "message": message_text
                    }
                    res = await client.post(url, data=params)
                    return {"status": "sent", "response": res.text, "phone": clean_phone}

                # 3. SSL Wireless
                elif provider == "ssl_wireless":
                    url = "https://smsplus.sslwireless.com/api/v3/send-sms"
                    payload = {
                        "api_token": api_key,
                        "sid": sender_id,
                        "msisdn": f"88{clean_phone}",
                        "sms": message_text,
                        "csms_id": f"sms_{clean_phone}"
                    }
                    res = await client.post(url, json=payload)
                    return {"status": "sent", "response": res.json() if res.status_code == 200 else res.text}

                # 4. BulkSMS BD
                elif provider == "bulksmsbd":
                    url = "http://bulksmsbd.net/api/smsapi"
                    params = {
                        "api_key": api_key,
                        "type": "text",
                        "number": clean_phone,
                        "senderid": sender_id,
                        "message": message_text
                    }
                    res = await client.post(url, data=params)
                    return {"status": "sent", "response": res.text}

                else:
                    return {"status": "unsupported_provider", "provider": provider}
        except Exception as e:
            logger.error(f"Failed to dispatch SMS to {clean_phone}: {str(e)}")
            return {"status": "error", "error": str(e)}
