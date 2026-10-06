"""Logging + optional Sentry error tracking.

* LOG_LEVEL (default INFO) controls verbosity; logs go to stdout in a single
  consistent format that Render / Docker / journald can collect.
* If SENTRY_DSN is set and ``sentry-sdk`` is installed, unhandled exceptions
  are reported to Sentry (with PII scrubbing left ON by default).
"""
import logging
import os


def setup_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
    else:
        root.setLevel(level)


def setup_sentry() -> None:
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        logging.getLogger(__name__).warning("SENTRY_DSN set but sentry-sdk is not installed")
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("ENVIRONMENT", "development"),
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
        send_default_pii=False,
    )
    logging.getLogger(__name__).info("Sentry error tracking enabled")
