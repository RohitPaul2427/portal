"""Bridge legacy ``EMERGENT_LLM_KEY`` checks to provider-specific keys.

Many modules still gate AI features on ``EMERGENT_LLM_KEY`` being set. When it
is not set but a real provider key is (ANTHROPIC_API_KEY / OPENAI_API_KEY /
GEMINI_API_KEY), we set a placeholder so those checks pass; the local
``emergentintegrations.llm.chat`` shim then uses the provider key.
Import this module once, right after loading .env and before any router.
"""
import os

from emergentintegrations.llm.chat import PLACEHOLDER_KEY

_PROVIDER_KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY")

if not os.environ.get("EMERGENT_LLM_KEY") and any(os.environ.get(k) for k in _PROVIDER_KEYS):
    os.environ["EMERGENT_LLM_KEY"] = PLACEHOLDER_KEY
