"""Fast unit tests that need no database or running server."""
import asyncio
import os

import pytest


def test_llm_shim_builds_vision_message():
    from emergentintegrations.llm.chat import ImageContent, LlmChat, UserMessage
    content = LlmChat._content(UserMessage(text="hi", file_contents=[ImageContent(image_base64="AAAA")]))
    assert content[0] == {"type": "text", "text": "hi"}
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,AAAA")


def test_llm_shim_requires_provider_key(monkeypatch):
    from emergentintegrations.llm.chat import PLACEHOLDER_KEY, LlmChat
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    chat = LlmChat(api_key=PLACEHOLDER_KEY).with_model("anthropic", "claude-haiku-4-5")
    with pytest.raises(RuntimeError):
        chat._resolve_key()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert chat._resolve_key() == "sk-test"


def test_mock_payments_disabled_by_default(monkeypatch):
    from fastapi import HTTPException
    from core.payment_mode import mock_payments_enabled, require_mock_payments
    monkeypatch.delenv("PAYMENT_MODE", raising=False)
    assert mock_payments_enabled() is False
    with pytest.raises(HTTPException) as e:
        require_mock_payments()
    assert e.value.status_code == 404
    monkeypatch.setenv("PAYMENT_MODE", "mock")
    assert mock_payments_enabled() is True


def test_paths_resolve_to_checkout():
    from core import paths
    assert os.path.isdir(os.path.join(paths.APP_ROOT, "backend"))


def test_verify_password_rejects_hash_as_password():
    from core.auth import get_password_hash, verify_password
    h = get_password_hash("Correct!Horse1")
    assert verify_password("Correct!Horse1", h)
    assert not verify_password(h, h)


def test_razorpay_signature_verification():
    import hashlib
    import hmac
    from core.razorpay_client import RazorpayUtility, SignatureVerificationError
    u = RazorpayUtility("secret")
    sig = hmac.new(b"secret", b"order_1|pay_1", hashlib.sha256).hexdigest()
    assert u.verify_payment_signature({"razorpay_order_id": "order_1", "razorpay_payment_id": "pay_1",
                                       "razorpay_signature": sig})
    with pytest.raises(SignatureVerificationError):
        u.verify_payment_signature({"razorpay_order_id": "order_1", "razorpay_payment_id": "pay_2",
                                    "razorpay_signature": sig})
