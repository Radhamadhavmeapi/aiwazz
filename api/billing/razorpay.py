"""Minimal Razorpay REST client (Subscriptions + Plans) and signature checks. Keys only from api/.env."""
import hashlib
import hmac

import httpx

from settings import get_settings

API = "https://api.razorpay.com/v1"


class RazorpayError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class Razorpay:
    def __init__(self, key_id: str, key_secret: str, transport: httpx.AsyncBaseTransport | None = None):
        self._auth = (key_id, key_secret)
        self._transport = transport

    async def _call(self, method: str, path: str, json: dict | None = None) -> dict:
        async with httpx.AsyncClient(base_url=API, auth=self._auth, timeout=20, transport=self._transport) as c:
            r = await c.request(method, path, json=json)
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("description") or r.text
            except ValueError:
                msg = r.text
            raise RazorpayError(r.status_code, msg[:300])
        return r.json()

    async def create_plan(self, period: str, amount_paise: int, name: str, description: str, notes: dict) -> dict:
        return await self._call("POST", "/plans", {
            "period": period, "interval": 1, "notes": notes,
            "item": {"name": name, "amount": amount_paise, "currency": "INR", "description": description}})

    async def get_plan(self, plan_id: str) -> dict:
        return await self._call("GET", f"/plans/{plan_id}")

    async def create_subscription(self, plan_id: str, total_count: int, notes: dict, offer_id: str = "") -> dict:
        body = {"plan_id": plan_id, "total_count": total_count, "customer_notify": 1, "notes": notes}
        if offer_id:
            body["offer_id"] = offer_id
        return await self._call("POST", "/subscriptions", body)

    async def get_subscription(self, sub_id: str) -> dict:
        return await self._call("GET", f"/subscriptions/{sub_id}")

    async def update_subscription(self, sub_id: str, plan_id: str, now: bool) -> dict:
        """Change plan. now=True: Razorpay charges the prorated difference immediately (upgrade); False: from the next
        cycle (downgrade). Razorpay allows this only for card-mandate subscriptions; other methods return an error."""
        return await self._call("PATCH", f"/subscriptions/{sub_id}", {
            "plan_id": plan_id, "schedule_change_at": "now" if now else "cycle_end", "customer_notify": 1})

    async def pause_subscription(self, sub_id: str) -> dict:
        return await self._call("POST", f"/subscriptions/{sub_id}/pause", {"pause_at": "now"})

    async def resume_subscription(self, sub_id: str) -> dict:
        return await self._call("POST", f"/subscriptions/{sub_id}/resume", {"resume_at": "now"})

    async def refund_payment(self, payment_id: str, amount_paise: int, notes: dict) -> dict:
        return await self._call("POST", f"/payments/{payment_id}/refund", {"amount": amount_paise, "speed": "normal", "notes": notes})

    async def cancel_subscription(self, sub_id: str, at_cycle_end: bool) -> dict:
        return await self._call("POST", f"/subscriptions/{sub_id}/cancel", {"cancel_at_cycle_end": 1 if at_cycle_end else 0})


def client() -> Razorpay:
    s = get_settings()
    return Razorpay(s.razorpay_key_id, s.razorpay_key_secret)


def _hmac(secret: str, msg: bytes) -> str:
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def checkout_signature_ok(payment_id: str, subscription_id: str, signature: str) -> bool:
    """Checkout handler signature for subscriptions: HMAC_SHA256(payment_id|subscription_id, key_secret)."""
    secret = get_settings().razorpay_key_secret
    return bool(secret) and hmac.compare_digest(_hmac(secret, f"{payment_id}|{subscription_id}".encode()), signature or "")


def webhook_signature_ok(raw_body: bytes, signature: str) -> bool:
    secret = get_settings().razorpay_webhook_secret
    return bool(secret) and hmac.compare_digest(_hmac(secret, raw_body), signature or "")
