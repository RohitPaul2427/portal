"""Document Security Service: Sensitivity Classification, Ephemeral Tokens, and Watermarking.

Provides:
- Sensitivity tier detection based on document type
- Ephemeral, short-lived preview tokens (15-minute default)
- Dynamic visual watermarking on PDF and image previews (viewer email, timestamp, case ref)
- Audit integration for preview and download events
"""
from __future__ import annotations

import io
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple

import jwt
from PIL import Image, ImageDraw, ImageFont
from PyPDF2 import PdfReader, PdfWriter
from reportlab.lib.colors import Color
from reportlab.pdfgen import canvas

from core.auth import JWT_SECRET
from core.case_workspace_models import DocumentSensitivityTier

logger = logging.getLogger(__name__)

SENSITIVE_DOC_TYPES = {
    "passport", "national_id", "aadhaar", "pcc", "police_clearance",
    "medical", "health_examination", "bank_statement", "proof_of_funds",
    "financial", "tax_return", "birth_certificate", "marriage_certificate"
}

RESTRICTED_DOC_TYPES = {
    "adoption", "protection_visa_statement", "legal_affidavit", "court_order"
}


def classify_sensitivity(doc_type: Optional[str]) -> DocumentSensitivityTier:
    """Classify document sensitivity tier by document type keyword."""
    if not doc_type:
        return DocumentSensitivityTier.STANDARD
    t = doc_type.lower().strip()
    for r in RESTRICTED_DOC_TYPES:
        if r in t:
            return DocumentSensitivityTier.HIGHLY_RESTRICTED
    for s in SENSITIVE_DOC_TYPES:
        if s in t:
            return DocumentSensitivityTier.SENSITIVE_IDENTITY
    return DocumentSensitivityTier.STANDARD


def generate_ephemeral_preview_token(
    doc_id: str,
    user_id: str,
    user_email: str,
    case_id: Optional[str] = None,
    expires_minutes: int = 15,
) -> str:
    """Generate a short-lived token specifically for previewing a document."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": user_email,
        "doc_id": doc_id,
        "case_id": case_id,
        "purpose": "doc_preview",
        "iat": int(now.timestamp()),
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def verify_ephemeral_preview_token(token: str) -> Dict[str, Any]:
    """Verify ephemeral preview token and return payload."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        if payload.get("purpose") != "doc_preview":
            raise ValueError("Invalid token purpose")
        return payload
    except Exception as e:
        raise ValueError(f"Invalid preview token: {e}") from e


def create_pdf_watermark_overlay(watermark_text: str, width: float, height: float) -> io.BytesIO:
    """Generate a single-page transparent watermark overlay with ReportLab."""
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(width, height))
    can.saveState()
    
    # 45-degree angle, semi-transparent grey
    can.setFont("Helvetica-Bold", 18)
    can.setFillColor(Color(0.5, 0.5, 0.5, alpha=0.22))
    can.rotate(45)

    # Repeating diagonal watermark grid
    for x in range(-int(height), int(width + height), 260):
        for y in range(-int(height), int(width + height), 120):
            can.drawString(x, y, watermark_text)

    can.restoreState()
    can.save()
    packet.seek(0)
    return packet


def watermark_pdf_bytes(pdf_bytes: bytes, watermark_text: str) -> bytes:
    """Stamp repeating watermark on all pages of a PDF."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()

        for page in reader.pages:
            w = float(page.mediabox.width)
            h = float(page.mediabox.height)
            overlay_stream = create_pdf_watermark_overlay(watermark_text, w, h)
            overlay_pdf = PdfReader(overlay_stream)
            overlay_page = overlay_pdf.pages[0]

            page.merge_page(overlay_page)
            writer.add_page(page)

        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()
    except Exception as e:
        logger.error("Failed to watermark PDF: %s", e)
        # Fall back to original bytes if watermarking fails
        return pdf_bytes


def watermark_image_bytes(image_bytes: bytes, watermark_text: str, mime_type: str = "image/jpeg") -> bytes:
    """Stamp semi-transparent diagonal text across an image using PIL."""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        txt_layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt_layer)

        w, h = img.size
        step_x = max(240, w // 3)
        step_y = max(120, h // 5)

        for x in range(0, w, step_x):
            for y in range(0, h, step_y):
                draw.text((x, y), watermark_text, fill=(128, 128, 128, 70))

        watermarked = Image.alpha_composite(img, txt_layer)
        out = io.BytesIO()
        if "png" in mime_type.lower():
            watermarked.save(out, format="PNG")
        else:
            watermarked.convert("RGB").save(out, format="JPEG", quality=85)
        return out.getvalue()
    except Exception as e:
        logger.error("Failed to watermark image: %s", e)
        return image_bytes
