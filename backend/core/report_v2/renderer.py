"""Phase 8 — Premium HTML→PDF Renderer (WeasyPrint + Jinja2).

Renders an Assessment Report snapshot into a magazine-quality PDF using
official LEAMSS brand colors (teal · warm orange · brand red).

Public entrypoint: ``render_pdf_v2(snapshot) -> bytes``

The function signature mirrors the legacy ReportLab ``render_pdf`` so
``routers/assessment_reports.py`` can switch implementations with zero
changes elsewhere.
"""
from __future__ import annotations

import base64
import logging
import mimetypes
import os
from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

# ─── Paths ──────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_TEMPLATES_DIR = _HERE / "templates"
_CSS_PATH = _HERE / "css" / "theme.css"
_ASSETS_DIR = _HERE.parent.parent / "assets"
_LOGO_PATH = _ASSETS_DIR / "leamss-logo.png"

# ─── Jinja env (singleton) ──────────────────────────────────────────────────
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _data_uri(path: Path) -> str | None:
    """Encode an image file as a base64 data URI for inline embedding."""
    if not path.exists():
        return None
    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _load_css() -> str:
    """Read the theme CSS once per call (small file, no caching needed)."""
    try:
        return _CSS_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.error("Theme CSS missing at %s", _CSS_PATH)
        return ""


def _find_browser_executable() -> str | None:
    for p in [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ]:
        if os.path.exists(p):
            return p
    return None


def _render_via_browser(html_str: str) -> bytes:
    import subprocess
    import tempfile

    browser = _find_browser_executable()
    if not browser:
        raise RuntimeError("No headless Chromium/Edge browser found on system")

    with tempfile.TemporaryDirectory() as tmpdir:
        in_html = os.path.join(tmpdir, "report.html")
        out_pdf = os.path.join(tmpdir, "report.pdf")
        with open(in_html, "w", encoding="utf-8") as f:
            f.write(html_str)

        cmd = [
            browser,
            "--headless",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={out_pdf}",
            in_html,
        ]
        res = subprocess.run(cmd, capture_output=True, timeout=60)
        if res.returncode != 0 or not os.path.exists(out_pdf):
            raise RuntimeError(f"Browser PDF export failed (exit code {res.returncode}): {res.stderr}")
        with open(out_pdf, "rb") as f:
            return f.read()


def render_pdf_v2(snapshot: Dict[str, Any]) -> bytes:
    """Render the LEAMSS Assessment Report PDF using the v2 (HTML→PDF) engine.

    Args:
        snapshot: Frozen snapshot dict (same shape produced by
            ``_build_snapshot`` in ``routers/assessment_reports.py``).
            Must include ``render_tier`` (teaser | full | proposal).

    Returns:
        PDF bytes ready to stream or persist.
    """
    snap = dict(snapshot)  # shallow copy — never mutate caller's payload
    snap.setdefault("render_tier", "full")

    css_text = _load_css()
    logo_uri = _data_uri(_LOGO_PATH)

    template = _env.get_template("base.html")
    html_str = template.render(
        snap=snap,
        css=css_text,
        logo_data_uri=logo_uri,
    )

    # 1. Try Headless Browser (Edge / Chrome) for pixel-perfect HTML UI/UX fidelity
    try:
        pdf_bytes = _render_via_browser(html_str)
        logger.info(
            "Phase 8 PDF v2 rendered via Browser Engine · snapshot=%s · tier=%s · size=%d bytes",
            snap.get("snapshot_id"), snap.get("render_tier"), len(pdf_bytes),
        )
        return pdf_bytes
    except Exception as browser_err:
        logger.warning("Browser rendering failed (%s), trying WeasyPrint", browser_err)

    # 2. Try WeasyPrint
    try:
        from weasyprint import HTML
        base_url = str(_HERE)  # so relative @font-face url() resolves
        pdf_bytes = HTML(string=html_str, base_url=base_url).write_pdf()
        logger.info(
            "Phase 8 PDF v2 rendered via WeasyPrint · snapshot=%s · tier=%s · size=%d bytes",
            snap.get("snapshot_id"), snap.get("render_tier"), len(pdf_bytes),
        )
        return pdf_bytes
    except Exception as e:
        logger.warning("WeasyPrint rendering failed (%s), falling back to ReportLab", e)
        from core.report_renderer import render_pdf
        return render_pdf(snapshot)


__all__ = ["render_pdf_v2"]

