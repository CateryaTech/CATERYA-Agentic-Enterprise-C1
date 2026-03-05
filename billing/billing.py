"""
Billing Integration — Stripe + Lightning Network
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech

Supports:
  - Stripe for credit card / recurring SaaS subscriptions
  - Lightning Network (LND/Strike) for crypto micro-payments
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

STRIPE_SECRET_KEY      = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET  = os.getenv("STRIPE_WEBHOOK_SECRET", "")
LN_INVOICE_URL         = os.getenv("LN_INVOICE_URL", "")   # LND or Strike API
LN_API_KEY             = os.getenv("LN_API_KEY", "")

# ── Pricing tiers ─────────────────────────────────────────────────────────────
PLANS = {
    "free": {
        "price_usd":      0,
        "stripe_price_id": "",
        "features":       ["5 runs/day", "1 tenant", "basic agents"],
        "cos_threshold":  0.7,
        "max_agents":     3,
    },
    "pro": {
        "price_usd":      49,
        "stripe_price_id": os.getenv("STRIPE_PRO_PRICE_ID", ""),
        "features":       ["500 runs/day", "10 tenants", "all agents", "monitoring"],
        "cos_threshold":  0.75,
        "max_agents":     10,
    },
    "enterprise": {
        "price_usd":      299,
        "stripe_price_id": os.getenv("STRIPE_ENTERPRISE_PRICE_ID", ""),
        "features":       ["unlimited runs", "unlimited tenants", "SLA", "priority support"],
        "cos_threshold":  0.8,
        "max_agents":     10,
    },
}


@dataclass
class BillingEvent:
    event_type: str
    tenant_id: str
    amount_cents: int
    currency: str
    provider: str
    metadata: Dict[str, Any]


# ── Stripe Integration ────────────────────────────────────────────────────────

class StripeClient:
    """
    Stripe billing client for SaaS subscriptions.

    Usage::

        client = StripeClient()
        checkout = client.create_checkout_session(
            tenant_id="acme",
            plan="pro",
            success_url="https://app.caterya.tech/billing/success",
            cancel_url="https://app.caterya.tech/billing/cancel",
        )
        redirect_user_to(checkout["url"])
    """

    def __init__(self):
        if not STRIPE_SECRET_KEY:
            raise RuntimeError("STRIPE_SECRET_KEY environment variable not set")
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        self._stripe = stripe

    def create_checkout_session(
        self,
        tenant_id: str,
        plan: str,
        success_url: str,
        cancel_url: str,
        customer_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        plan_config = PLANS.get(plan, PLANS["pro"])
        price_id    = plan_config.get("stripe_price_id")

        if not price_id:
            raise ValueError(f"Stripe price_id not configured for plan '{plan}'")

        params = {
            "mode": "subscription",
            "payment_method_types": ["card"],
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": success_url + "?session_id={CHECKOUT_SESSION_ID}",
            "cancel_url":  cancel_url,
            "metadata": {"tenant_id": tenant_id, "plan": plan},
        }
        if customer_email:
            params["customer_email"] = customer_email

        session = self._stripe.checkout.Session.create(**params)
        logger.info("Checkout session created | tenant=%s plan=%s", tenant_id, plan)
        return {"url": session.url, "session_id": session.id}

    def create_portal_session(self, stripe_customer_id: str, return_url: str) -> str:
        session = self._stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=return_url,
        )
        return session.url

    def handle_webhook(self, payload: bytes, sig_header: str) -> Optional[BillingEvent]:
        try:
            event = self._stripe.Webhook.construct_event(
                payload, sig_header, STRIPE_WEBHOOK_SECRET
            )
        except Exception as exc:
            logger.warning("Webhook verification failed: %s", exc)
            return None

        e_type  = event["type"]
        obj     = event["data"]["object"]
        meta    = obj.get("metadata", {})
        tenant  = meta.get("tenant_id", "unknown")

        if e_type == "checkout.session.completed":
            logger.info("Subscription created | tenant=%s", tenant)
            return BillingEvent(
                event_type="subscription_created",
                tenant_id=tenant,
                amount_cents=obj.get("amount_total", 0),
                currency=obj.get("currency", "usd"),
                provider="stripe",
                metadata=meta,
            )
        elif e_type == "customer.subscription.deleted":
            logger.info("Subscription cancelled | tenant=%s", tenant)
            return BillingEvent(
                event_type="subscription_cancelled",
                tenant_id=tenant,
                amount_cents=0,
                currency="usd",
                provider="stripe",
                metadata=meta,
            )
        elif e_type == "invoice.payment_failed":
            logger.warning("Payment failed | tenant=%s", tenant)
            return BillingEvent(
                event_type="payment_failed",
                tenant_id=tenant,
                amount_cents=obj.get("amount_due", 0),
                currency=obj.get("currency", "usd"),
                provider="stripe",
                metadata=meta,
            )

        return None

    def get_usage_record(self, subscription_item_id: str, quantity: int, timestamp: Optional[int] = None) -> Dict:
        """Record metered usage (for pay-per-run billing)."""
        record = self._stripe.SubscriptionItem.create_usage_record(
            subscription_item_id,
            quantity=quantity,
            timestamp=timestamp or int(time.time()),
            action="increment",
        )
        return {"id": record.id, "quantity": record.quantity}


# ── Lightning Network Integration ─────────────────────────────────────────────

class LightningClient:
    """
    Lightning Network (LND/Strike) client for crypto micro-payments.

    Usage::

        client = LightningClient()
        invoice = client.create_invoice(
            amount_sats=1000,
            description="CATERYA Pro — 1 month",
            tenant_id="acme",
        )
        # User pays invoice["payment_request"] via Lightning wallet
    """

    def __init__(self):
        if not LN_INVOICE_URL:
            raise RuntimeError("LN_INVOICE_URL environment variable not set")
        self.invoice_url = LN_INVOICE_URL
        self.api_key     = LN_API_KEY

    async def create_invoice(
        self,
        amount_sats: int,
        description: str,
        tenant_id: str,
        expiry_seconds: int = 3600,
    ) -> Dict[str, Any]:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.invoice_url}/v1/invoices",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "value":   amount_sats,
                    "memo":    description,
                    "expiry":  expiry_seconds,
                    "private": True,
                },
                timeout=10,
            )

        if resp.status_code != 200:
            raise RuntimeError(f"LN invoice creation failed: {resp.status_code} {resp.text}")

        data = resp.json()
        logger.info("LN invoice created | tenant=%s sats=%d", tenant_id, amount_sats)
        return {
            "payment_request": data.get("payment_request"),
            "r_hash":          data.get("r_hash"),
            "expiry":          expiry_seconds,
            "amount_sats":     amount_sats,
            "tenant_id":       tenant_id,
        }

    async def check_invoice(self, r_hash: str) -> Dict[str, Any]:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.invoice_url}/v1/invoice/{r_hash}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
        data = resp.json()
        return {
            "settled":     data.get("settled", False),
            "amount_sats": data.get("value", 0),
            "settled_at":  data.get("settle_date"),
        }

    @staticmethod
    def usd_to_sats(usd_amount: float, btc_price_usd: float = 65000.0) -> int:
        """Convert USD to satoshis (1 BTC = 100,000,000 sats)."""
        btc_amount = usd_amount / btc_price_usd
        return int(btc_amount * 100_000_000)


# ── Plan enforcement ──────────────────────────────────────────────────────────

def get_plan_limits(plan: str) -> Dict[str, Any]:
    return PLANS.get(plan, PLANS["free"])


def check_plan_limit(tenant_id: str, plan: str, metric: str, current: int) -> bool:
    """Return True if within plan limits, False if exceeded."""
    limits = get_plan_limits(plan)
    limit_map = {
        "daily_runs":   {"free": 5, "pro": 500, "enterprise": float("inf")},
        "max_agents":   {"free": 3, "pro": 10,  "enterprise": 10},
        "max_tenants":  {"free": 1, "pro": 10,  "enterprise": float("inf")},
    }
    limit = limit_map.get(metric, {}).get(plan, float("inf"))
    within = current <= limit
    if not within:
        logger.warning("Plan limit exceeded | tenant=%s plan=%s metric=%s current=%d limit=%s",
                       tenant_id, plan, metric, current, limit)
    return within
