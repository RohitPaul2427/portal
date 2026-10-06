"""Central switch for MOCK (fake) payment endpoints.

SECURITY: mock payment routes mark fees as PAID without any money moving.
They are disabled unless the server is explicitly started with
``PAYMENT_MODE=mock`` (local development / demos only). Never set this in
production.
"""
import os

from fastapi import HTTPException


def mock_payments_enabled() -> bool:
    return os.environ.get("PAYMENT_MODE", "").strip().lower() == "mock"


def require_mock_payments() -> None:
    if not mock_payments_enabled():
        # 404 so the endpoint is indistinguishable from "does not exist" in production
        raise HTTPException(status_code=404, detail="Not found")
