"""Local drop-in replacement for the private ``emergentintegrations`` package.

The portal was originally generated on the Emergent platform, which injected a
private ``emergentintegrations`` library and a universal ``EMERGENT_LLM_KEY``.
That package is not on PyPI, so every AI / Stripe feature crashed on any other
host. This module re-implements the small subset of its API the portal uses on
top of public libraries:

* ``emergentintegrations.llm.chat``  -> LiteLLM (Anthropic / OpenAI / Gemini)
* ``emergentintegrations.payments.stripe.checkout`` -> official ``stripe`` SDK

Keys are taken from the provider-specific env vars (ANTHROPIC_API_KEY,
OPENAI_API_KEY, GEMINI_API_KEY). See ``llm/chat.py``.
"""
