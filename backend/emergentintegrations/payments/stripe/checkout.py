"""Minimal Stripe Checkout wrapper matching the API the portal used from
``emergentintegrations.payments.stripe.checkout``, built on the official SDK.

Note: LEAMSS primarily uses Razorpay (``core/razorpay_client.py``). Stripe is
only used when STRIPE_API_KEY is configured.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class CheckoutSessionRequest:
    amount: float
    currency: str
    success_url: str
    cancel_url: str
    metadata: Dict[str, str] = field(default_factory=dict)
    stripe_price_id: Optional[str] = None
    quantity: int = 1


@dataclass
class CheckoutSessionResponse:
    url: str
    session_id: str


@dataclass
class CheckoutStatusResponse:
    status: str
    payment_status: str
    amount_total: int
    currency: str
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class WebhookResponse:
    event_type: str
    event_id: str
    session_id: Optional[str]
    payment_status: Optional[str]
    metadata: Dict[str, str] = field(default_factory=dict)


class StripeCheckout:
    def __init__(self, api_key: str, webhook_url: str = "", webhook_secret: Optional[str] = None):
        import stripe

        self._stripe = stripe
        self.api_key = api_key
        self.webhook_url = webhook_url
        self.webhook_secret = webhook_secret or os.environ.get("STRIPE_WEBHOOK_SECRET")

    async def create_checkout_session(self, req: CheckoutSessionRequest) -> CheckoutSessionResponse:
        def _create():
            if req.stripe_price_id:
                line_items = [{"price": req.stripe_price_id, "quantity": req.quantity}]
            else:
                line_items = [{
                    "price_data": {
                        "currency": req.currency.lower(),
                        "product_data": {"name": req.metadata.get("description", "LEAMSS payment")},
                        "unit_amount": int(round(float(req.amount) * 100)),
                    },
                    "quantity": req.quantity,
                }]
            return self._stripe.checkout.Session.create(
                api_key=self.api_key,
                mode="payment",
                line_items=line_items,
                success_url=req.success_url,
                cancel_url=req.cancel_url,
                metadata=req.metadata,
            )

        s = await asyncio.to_thread(_create)
        return CheckoutSessionResponse(url=s.url, session_id=s.id)

    async def get_checkout_status(self, session_id: str) -> CheckoutStatusResponse:
        s = await asyncio.to_thread(self._stripe.checkout.Session.retrieve, session_id, api_key=self.api_key)
        return CheckoutStatusResponse(
            status=s.status, payment_status=s.payment_status,
            amount_total=s.amount_total or 0, currency=s.currency or "",
            metadata=dict(s.metadata or {}),
        )

    async def handle_webhook(self, body: bytes, signature: Optional[str]) -> WebhookResponse:
        # SECURITY: webhook signature MUST be verified.
        if not self.webhook_secret:
            raise ValueError("STRIPE_WEBHOOK_SECRET is not configured; refusing unverified webhook")
        event = self._stripe.Webhook.construct_event(body, signature, self.webhook_secret)
        obj: Dict[str, Any] = event["data"]["object"]
        return WebhookResponse(
            event_type=event["type"], event_id=event["id"],
            session_id=obj.get("id"), payment_status=obj.get("payment_status"),
            metadata=dict(obj.get("metadata") or {}),
        )


__all__ = ["StripeCheckout", "CheckoutSessionRequest", "CheckoutSessionResponse",
           "CheckoutStatusResponse", "WebhookResponse"]
