"""LiteLLM-backed implementation of the ``LlmChat`` API used across the portal.

Usage (unchanged from the original library)::

    chat = LlmChat(api_key=KEY, session_id="x", system_message="...") \
        .with_model("anthropic", "claude-sonnet-4-6") \
        .with_params(max_tokens=2000)
    text = await chat.send_message(UserMessage(text="hello"))

Provider keys are resolved in this order:
1. Provider env var: ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY
2. The ``api_key`` passed to ``LlmChat`` (unless it is the placeholder
   ``"provider-keys"`` set automatically by ``core.llm_env``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_PROVIDER_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "google": "GEMINI_API_KEY",
}
_PROVIDER_PREFIX = {"anthropic": "anthropic", "openai": "openai", "gemini": "gemini", "google": "gemini"}
PLACEHOLDER_KEY = "provider-keys"


@dataclass
class ImageContent:
    image_base64: str
    mime_type: str = "image/png"


@dataclass
class FileContentWithMimeType:
    file_path: str
    mime_type: str


@dataclass
class UserMessage:
    text: str = ""
    file_contents: List[Any] = field(default_factory=list)


class LlmChat:
    def __init__(self, api_key: Optional[str] = None, session_id: str = "", system_message: str = ""):
        self.api_key = api_key
        self.session_id = session_id
        self.system_message = system_message or ""
        self.provider = "openai"
        self.model = "gpt-4o"
        self.params: Dict[str, Any] = {}
        self.history: List[Dict[str, Any]] = []

    def with_model(self, provider: str, model: str) -> "LlmChat":
        self.provider = (provider or "openai").lower()
        self.model = model
        return self

    def with_params(self, **params: Any) -> "LlmChat":
        self.params.update(params)
        return self

    def _resolve_key(self) -> Optional[str]:
        env_key = os.environ.get(_PROVIDER_ENV.get(self.provider, ""), "")
        if env_key:
            return env_key
        if self.api_key and self.api_key != PLACEHOLDER_KEY:
            return self.api_key
        raise RuntimeError(
            f"No API key for provider '{self.provider}'. Set {_PROVIDER_ENV.get(self.provider, 'the provider key')}."
        )

    @staticmethod
    def _content(msg: UserMessage) -> Any:
        if not msg.file_contents:
            return msg.text
        parts: List[Dict[str, Any]] = [{"type": "text", "text": msg.text}]
        for fc in msg.file_contents:
            if isinstance(fc, ImageContent):
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{fc.mime_type};base64,{fc.image_base64}"},
                })
            elif isinstance(fc, FileContentWithMimeType):
                import base64
                with open(fc.file_path, "rb") as fh:
                    b64 = base64.b64encode(fh.read()).decode()
                parts.append({"type": "image_url", "image_url": {"url": f"data:{fc.mime_type};base64,{b64}"}})
        return parts

    async def send_message(self, message: UserMessage) -> str:
        import litellm  # imported lazily: heavy module

        messages: List[Dict[str, Any]] = []
        if self.system_message:
            messages.append({"role": "system", "content": self.system_message})
        messages.extend(self.history)
        user_turn = {"role": "user", "content": self._content(message)}
        messages.append(user_turn)

        prefix = _PROVIDER_PREFIX.get(self.provider, self.provider)
        model = self.model if "/" in self.model else f"{prefix}/{self.model}"
        params = {"max_tokens": 4096, "timeout": 120, **self.params}

        resp = await litellm.acompletion(model=model, messages=messages, api_key=self._resolve_key(), **params)
        text = resp.choices[0].message.content or ""
        self.history.extend([user_turn, {"role": "assistant", "content": text}])
        return text


__all__ = ["LlmChat", "UserMessage", "ImageContent", "FileContentWithMimeType"]
