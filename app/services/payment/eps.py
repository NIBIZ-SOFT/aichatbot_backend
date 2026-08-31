import time
import uuid
import hmac
import hashlib
import base64
import httpx
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class EpsService:
    """
    Official EPS (Easy Payment System) Payment Gateway Service
    Direct 1-to-1 parity with official EPS Gateway Documentation & PHP implementation:
    - Auth Token Generation with HMAC-SHA512 header (POST /v1/Auth/GetToken)
    - Payment Initialization (POST /v1/EPSEngine/InitializeEPS)
    - Transaction Status Verification (GET /v1/EPSEngine/CheckMerchantTransactionStatus)
    """
    def __init__(
        self,
        base_url: str = "https://sandboxpgapi.eps.com.bd",
        username: str = "Epsdemo@gmail.com",
        password: str = "Epsdemo258@",
        hash_key: str = "FHZxyzeps56789gfhg678ygu876o=",
        merchant_id: str = "29e86e70-0ac6-45eb-ba04-9fcb0aaed12a",
        store_id: str = "d44e705f-9e3a-41de-98b1-1674631637da",
        merchant_number: str = "01700000000"
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.hash_key = hash_key
        self.merchant_id = merchant_id
        self.store_id = store_id
        self.merchant_number = merchant_number
        self._token: Optional[str] = None
        self._token_expiry: float = 0

    @staticmethod
    def generate_hash(data: str, secret_key: str) -> str:
        """
        Official EPS Hash Algorithm:
        base64_encode(hash_hmac('sha512', utf8_encode($data), $secretKey, true))
        """
        signature = hmac.new(
            secret_key.encode("utf-8"),
            data.encode("utf-8"),
            hashlib.sha512
        ).digest()
        return base64.b64encode(signature).decode("utf-8")

    def get_config(self) -> Dict[str, Any]:
        return {
            "base_url": self.base_url,
            "username": self.username,
            "password": self.password,
            "hash_key": self.hash_key,
            "merchant_id": self.merchant_id,
            "store_id": self.store_id,
            "merchant_number": getattr(self, "merchant_number", "01700000000"),
            "is_sandbox": "sandbox" in self.base_url.lower()
        }

    def update_config(self, config: Dict[str, Any]):
        if "base_url" in config and config["base_url"]:
            self.base_url = config["base_url"].rstrip("/")
        if "username" in config and config["username"]:
            self.username = config["username"]
        if "password" in config and config["password"]:
            self.password = config["password"]
        if "hash_key" in config and config["hash_key"]:
            self.hash_key = config["hash_key"]
        if "merchant_id" in config and config["merchant_id"]:
            self.merchant_id = config["merchant_id"]
        if "store_id" in config and config["store_id"]:
            self.store_id = config["store_id"]
        if "merchant_number" in config and config["merchant_number"]:
            self.merchant_number = config["merchant_number"]
        if "is_sandbox" in config:
            if config["is_sandbox"] and "sandbox" not in self.base_url.lower():
                self.base_url = "https://sandboxpgapi.eps.com.bd"
            elif not config["is_sandbox"] and "sandbox" in self.base_url.lower():
                self.base_url = "https://pgapi.eps.com.bd"
        # Invalidate token cache on settings change
        self._token = None
        self._token_expiry = 0

    async def grant_token(self) -> str:
        """
        Official Endpoint: POST /v1/Auth/GetToken
        Header: x-hash = generateHash(userName, hash_key)
        """
        now = time.time()
        if self._token and now < (self._token_expiry - 120):
            return self._token

        url = f"{self.base_url}/v1/Auth/GetToken"
        x_hash = self.generate_hash(self.username, self.hash_key)
        headers = {
            "Content-Type": "application/json",
            "x-hash": x_hash
        }
        payload = {
            "userName": self.username,
            "password": self.password
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.post(url, json=payload, headers=headers)
            data = res.json()
            if res.status_code == 200 and ("token" in data or "data" in data):
                token = data.get("token") or data.get("data", {}).get("token")
                if token:
                    self._token = token
                    self._token_expiry = now + 3500
                    logger.info("Successfully granted new official EPS token")
                    return self._token

            error_msg = data.get("ErrorMessage") or data.get("message") or f"HTTP {res.status_code}"
            logger.error(f"EPS GetToken failed: {error_msg}")
            raise RuntimeError(f"Failed to authenticate with EPS Gateway: {error_msg}")

    async def initialize_payment(
        self,
        amount: float,
        merchant_transaction_id: str,
        customer_order_id: Optional[str] = None,
        customer_name: str = "Valued Customer",
        customer_email: str = "customer@example.com",
        customer_phone: str = "01700000000",
        customer_address: str = "Dhaka, Bangladesh",
        customer_city: str = "Dhaka",
        customer_state: str = "Dhaka",
        customer_postcode: str = "1230",
        product_name: str = "AI SaaS Subscription",
        product_category: str = "Software",
        callback_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Official Endpoint: POST /v1/EPSEngine/InitializeEPS
        Header: x-hash = generateHash(merchantTransactionId, hash_key)
        Header: Authorization = Bearer {token}
        """
        from app.core.config import settings
        if not callback_url:
            callback_url = f"{settings.FRONTEND_URL}/subscription/eps-callback?merchantTransactionId={merchant_transaction_id}"
        elif "?" in callback_url:
            callback_url += f"&merchantTransactionId={merchant_transaction_id}"
        else:
            callback_url += f"?merchantTransactionId={merchant_transaction_id}"

        # Generate unique CustomerOrderId required by EPS API
        order_id = customer_order_id or f"ORD{int(time.time())}{uuid.uuid4().hex[:4].upper()}"

        token = await self.grant_token()
        url = f"{self.base_url}/v1/EPSEngine/InitializeEPS"
        x_hash = self.generate_hash(merchant_transaction_id, self.hash_key)
        headers = {
            "Content-Type": "application/json",
            "x-hash": x_hash,
            "Authorization": f"Bearer {token}"
        }
        payment_data = {
            "merchantId": self.merchant_id,
            "storeId": self.store_id,
            "CustomerOrderId": order_id,
            "merchantTransactionId": merchant_transaction_id,
            "transactionTypeId": 1,
            "totalAmount": round(float(amount), 2),
            "successUrl": callback_url,
            "failUrl": callback_url,
            "cancelUrl": callback_url,
            "customerName": customer_name,
            "customerEmail": customer_email,
            "customerAddress": customer_address,
            "customerCity": customer_city,
            "customerState": customer_state,
            "customerPostcode": customer_postcode,
            "customerCountry": "BD",
            "customerPhone": customer_phone,
            "productName": product_name,
            "productProfile": "general",
            "productCategory": product_category
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.post(url, json=payment_data, headers=headers)
            data = res.json()
            redirect_url = data.get("RedirectURL") or data.get("redirectUrl") or data.get("data", {}).get("RedirectURL")
            if res.status_code == 200 and redirect_url:
                return {
                    "status": "success",
                    "merchantTransactionId": merchant_transaction_id,
                    "transactionId": data.get("TransactionId"),
                    "redirectURL": redirect_url,
                    "totalAmount": amount,
                    "currency": "BDT",
                    "is_sandbox": "sandbox" in self.base_url.lower()
                }

            error_msg = data.get("ErrorMessage") or f"EPS API Error Code: {data.get('ErrorCode')}"
            logger.error(f"EPS InitializeEPS failed: {error_msg}")
            raise RuntimeError(f"EPS Initialization Error: {error_msg}")

    async def verify_transaction(self, merchant_transaction_id: str) -> Dict[str, Any]:
        """
        Official Endpoint: GET /v1/EPSEngine/CheckMerchantTransactionStatus?merchantTransactionId={merchant_transaction_id}
        Header: x-hash = generateHash(merchantTransactionId, hash_key)
        Header: Authorization = Bearer {token}
        """
        token = await self.grant_token()
        url = f"{self.base_url}/v1/EPSEngine/CheckMerchantTransactionStatus?merchantTransactionId={merchant_transaction_id}"
        x_hash = self.generate_hash(merchant_transaction_id, self.hash_key)
        headers = {
            "x-hash": x_hash,
            "Authorization": f"Bearer {token}"
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.get(url, headers=headers)
            data = res.json()
            
            # EPS official status response keys: Status, transactionStatus, status
            status = None
            if isinstance(data, dict):
                status = (
                    data.get("Status") or
                    data.get("transactionStatus") or
                    data.get("status") or
                    data.get("data", {}).get("Status") or
                    data.get("data", {}).get("transactionStatus")
                )
            
            status_str = str(status).upper() if status else "UNKNOWN"
            if res.status_code == 200 and status_str in ["SUCCESS", "COMPLETED"]:
                return {
                    "status": "SUCCESS",
                    "merchantTransactionId": merchant_transaction_id,
                    "epsTransactionId": data.get("EPSTransactionId"),
                    "amount": data.get("TotalAmount"),
                    "raw": data,
                    "is_sandbox": "sandbox" in self.base_url.lower()
                }
            elif status_str in ["FAILED", "FAILURE", "CANCEL", "CANCELED"]:
                return {
                    "status": status_str,
                    "merchantTransactionId": merchant_transaction_id,
                    "epsTransactionId": data.get("EPSTransactionId"),
                    "raw": data,
                    "is_sandbox": "sandbox" in self.base_url.lower()
                }
            else:
                error_msg = data.get("ErrorMessage") or f"Status: {status_str}"
                logger.warning(f"EPS verify transaction returned: {data}")
                return {
                    "status": status_str,
                    "merchantTransactionId": merchant_transaction_id,
                    "errorMessage": error_msg,
                    "raw": data,
                    "is_sandbox": "sandbox" in self.base_url.lower()
                }

eps_service = EpsService()
