"""Shared network settings.

SECURITY: TLS certificate verification is ON by default. If you are behind a
corporate proxy that re-signs HTTPS traffic, point SSL_CERT_FILE at the proxy's
CA bundle instead of disabling verification. ``INSECURE_SKIP_TLS_VERIFY=1``
exists only as a last-resort local-development escape hatch.
"""
import os

HTTP_VERIFY = os.environ.get("INSECURE_SKIP_TLS_VERIFY") != "1"
DEFAULT_TIMEOUT = float(os.environ.get("HTTP_DEFAULT_TIMEOUT", "30"))
