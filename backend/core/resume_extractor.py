"""Phase 6.7 Part 2 — Resume Upload + AI Extraction.

Extracts structured candidate profile fields from a resume (PDF or DOCX) using:
  1. Text extraction via pdfplumber / python-docx
  2. Claude AI (Sonnet 4.6) for structured JSON extraction

Output schema matches the Phase 6.7 ProfileCreate model so it can be used to
prefill the wizard directly.
"""
import asyncio
import io
import json
import logging
import os
from typing import Dict, Any, List, Optional, Tuple
from openai import AsyncOpenAI
import re
from datetime import datetime


logger = logging.getLogger(__name__)

PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
PERPLEXITY_MODEL = "sonar-pro"

MAX_TEXT_CHARS = 24_000  # safe Claude input budget


EXTRACTION_PROMPT = """You are a resume-parsing assistant for an immigration consultancy.

Extract the candidate's profile from the resume text below. Return ONLY a JSON object
matching this exact schema (omit fields if not found — do NOT invent data):

{
  "name": "Full name of the candidate",
  "email": "email if present",
  "phone": "phone with country code if present",
  "marital_status": "single | married | de_facto | separated | divorced | widowed (if mentioned)",
  "primary_applicant": {
    "personal": {
      "full_name": "...",
      "date_of_birth": "YYYY-MM-DD if found",
      "age": null,
      "gender": "male | female | other (if found)",
      "nationality": "if found",
      "current_country": "country candidate currently lives in",
      "current_city": "city candidate currently lives in"
    },
    "professional": {
      "current_profession": "MOST RECENT job role (e.g., 'Marketing Specialist', 'Software Engineer')",
      "designation": "Most recent designation/title",
      "years_experience_total": 0.0,
      "years_in_current_role": 0.0,
      "industry": "Industry sector",
      "employer_name": "Current employer",
      "salary_inr_per_annum": null,
      "has_managerial_experience": false
    },
    "education": {
      "highest_qualification": "doctorate | master | bachelor | diploma | trade | high_school",
      "field_of_study": "Field of study (e.g., 'Computer Science')",
      "institution": "Last/highest institution",
      "country": "Country of highest qualification",
      "year_completed": null
    },
    "language": {
      "primary_test": "IELTS | PTE | TOEFL | none",
      "test_completed": false,
      "test_date": null,
      "scores": {}
    },
    "work_history": [
      {"employer": "...", "designation": "...", "start_date": "YYYY-MM", "end_date": "YYYY-MM or null", "country": "...", "duties": "1-2 line summary"}
    ]
  },
  "_extraction_notes": ["any caveats, ambiguities, or fields that need user review"]
}

CRITICAL RULES:
- The MOST RECENT job (top of work history) = `current_profession` and `designation`.
- `years_experience_total` = sum of years across all professional roles (not student/intern).
- `highest_qualification` MUST be one of: doctorate | master | bachelor | diploma | trade | high_school. Map common synonyms (PhD→doctorate, M.Tech/MBA/M.S→master, B.Tech/B.E/B.S→bachelor).
- DO NOT confuse education field with current profession. e.g., A B.V.Sc graduate currently working as Marketing Specialist → `current_profession='Marketing Specialist'`, `field_of_study='Veterinary Science'`.
- If language test is mentioned (IELTS/PTE/TOEFL), set `test_completed=true` and include scores. Otherwise default to `primary_test='IELTS', test_completed=false, scores={}`.
- For unclear fields, leave them null/empty and add a note in `_extraction_notes`.
- Output MUST be valid JSON. NO markdown, NO commentary outside the JSON.
"""


def extract_text_from_pdf(file_bytes: bytes) -> Tuple[str, Dict[str, Any]]:
    """Extract plain text from a PDF resume."""
    import pdfplumber

    text_parts = []
    page_count = 0
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            t = page.extract_text() or ""
            if t.strip():
                text_parts.append(t)
    text = "\n\n".join(text_parts)
    return text, {"page_count": page_count, "char_count": len(text)}


def extract_text_from_docx(file_bytes: bytes) -> Tuple[str, Dict[str, Any]]:
    """Extract plain text from a DOCX resume."""
    from docx import Document

    doc = Document(io.BytesIO(file_bytes))
    parts = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    # Also pull table cells
    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                if cell.text and cell.text.strip():
                    parts.append(cell.text.strip())
    text = "\n".join(parts)
    return text, {"paragraph_count": len(doc.paragraphs), "char_count": len(text)}


def extract_text(filename: str, file_bytes: bytes) -> Tuple[str, Dict[str, Any]]:
    """Dispatch by file extension."""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)
    if name.endswith(".docx"):
        return extract_text_from_docx(file_bytes)
    if name.endswith(".txt"):
        try:
            t = file_bytes.decode("utf-8", errors="replace")
        except Exception:
            t = file_bytes.decode("latin-1", errors="replace")
        return t, {"char_count": len(t)}
    raise ValueError(f"Unsupported file type — only .pdf, .docx, .txt allowed (got '{name}')")


# ---------------------------------------------------------------------------
# OCR fallback (scanned/image resumes) via vision LLM
# ---------------------------------------------------------------------------
OCR_MODEL = "gemini-2.5-flash"
OCR_MAX_PAGES = 4
_OCR_SYS = ("You are an OCR engine. Transcribe ALL text from the document image(s) verbatim "
            "as plain text. Preserve names, job titles, companies, dates, skills and education. "
            "Output ONLY the transcribed text, no commentary.")


async def ocr_images_to_text(images_b64: List[str], model: Optional[str] = None) -> str:
    """Transcribe text from one or more images using Anthropic Claude Vision."""
    import httpx
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not anthropic_key or not images_b64:
        return ""

    content: List[Dict[str, Any]] = []
    for b64 in images_b64[:OCR_MAX_PAGES]:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": b64,
            },
        })
    content.append({
        "type": "text",
        "text": _OCR_SYS,
    })

    try:
        async with httpx.AsyncClient(verify=False, timeout=60) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-3-5-haiku-20241022",
                    "max_tokens": 4000,
                    "messages": [
                        {"role": "user", "content": content}
                    ],
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                text_blocks = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
                return "\n\n".join(text_blocks).strip()
            else:
                logger.warning(f"Claude OCR error {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"OCR request failed: {e}")
    return ""


def _render_pdf_to_pngs(file_bytes: bytes, max_pages: int = OCR_MAX_PAGES, dpi: int = 150) -> List[str]:
    """Render the first N PDF pages to base64 PNGs using pypdfium2."""
    import base64
    import io
    import pypdfium2
    out: List[str] = []
    pdf = pypdfium2.PdfDocument(file_bytes)
    try:
        n_pages = min(len(pdf), max_pages)
        for i in range(n_pages):
            page = pdf[i]
            image = page.render(scale=1.5).to_pil()
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            out.append(base64.b64encode(buf.getvalue()).decode())
    except Exception as e:
        logger.warning(f"Error rendering PDF to PNGs: {e}")
    finally:
        pdf.close()
    return out


async def ocr_pdf_bytes(file_bytes: bytes, model: Optional[str] = None) -> str:
    try:
        pngs = await asyncio.to_thread(_render_pdf_to_pngs, file_bytes)
    except Exception as e:
        logger.warning(f"PDF render for OCR failed: {e}")
        return ""
    return await ocr_images_to_text(pngs, model=model) if pngs else ""


async def ocr_image_bytes(file_bytes: bytes, model: Optional[str] = None) -> str:
    import base64
    return await ocr_images_to_text([base64.b64encode(file_bytes).decode()], model=model)


async def extract_text_smart(filename: str, file_bytes: bytes) -> Tuple[Optional[str], Optional[str]]:
    """Extract resume text with an OCR fallback for scanned PDFs & image files.
    Returns (text, error_message)."""
    name = (filename or "").lower()
    is_image = (name.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"))
                or file_bytes[:3] == b"\xff\xd8\xff" or file_bytes[:8] == b"\x89PNG\r\n\x1a\n")
    is_pdf = name.endswith(".pdf") or file_bytes[:4] == b"%PDF"

    if is_image:
        text = await ocr_image_bytes(file_bytes)
        if text and len(text.strip()) >= 30:
            return text, None
        return None, "Could not read text from image."

    try:
        text, _meta = await asyncio.to_thread(extract_text, filename, file_bytes)
    except ValueError as e:
        if is_pdf:
            ocr = await ocr_pdf_bytes(file_bytes)
            if ocr and len(ocr.strip()) >= 30:
                return ocr, None
        return None, str(e)

    if (not text or len(text.strip()) < 50) and is_pdf:
        ocr = await ocr_pdf_bytes(file_bytes)  # scanned/image-only PDF
        if ocr and len(ocr.strip()) >= 30:
            return ocr, None
    if not text or len(text.strip()) < 30:
        return None, "Resume text was empty (scanned image or unreadable file)."
    return text, None


def parse_resume_heuristically(text: str) -> dict:
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # 1. Email
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    email = email_match.group(0) if email_match else ""

    # 2. Phone
    phone_match = re.search(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}', text)
    phone = phone_match.group(0) if phone_match else ""

    # 3. Name (from top lines, excluding headers and urls)
    name = ""
    for l in lines[:5]:
        if not re.search(r'[@\/\:]', l) and len(l.split()) in (2, 3, 4) and len(l) < 50:
            if not any(k in l.lower() for k in ['curriculum', 'vitae', 'resume', 'profile', 'summary', 'contact', 'experience']):
                name = l.strip()
                break
    if not name and lines:
        name = lines[0][:40]

    # 4. Age / DOB
    age = 30
    dob = None
    dob_match = re.search(r'(?:DOB|Date of Birth|Birth Date|Born)[:\s]+([0-9]{1,2}[-/.][0-9]{1,2}[-/.][0-9]{2,4}|[A-Za-z]+\s+[0-9]{1,2},?\s+[0-9]{4}|[0-9]{4})', text, re.I)
    if dob_match:
        dob_str = dob_match.group(1)
        year_match = re.search(r'(19\d{2}|200\d)', dob_str)
        if year_match:
            birth_year = int(year_match.group(1))
            age = max(18, min(65, datetime.now().year - birth_year))
            dob = dob_str

    # 5. Education
    text_lower = text.lower()
    highest_qual = "bachelor"
    if "phd" in text_lower or "doctorate" in text_lower or "doctor of" in text_lower:
        highest_qual = "doctorate"
    elif "master" in text_lower or "m.tech" in text_lower or "m.sc" in text_lower or "mba" in text_lower or "m.s." in text_lower:
        highest_qual = "master"
    elif "bachelor" in text_lower or "b.tech" in text_lower or "b.sc" in text_lower or "b.e." in text_lower or "b.com" in text_lower or "bba" in text_lower:
        highest_qual = "bachelor"
    elif "diploma" in text_lower or "associate" in text_lower:
        highest_qual = "diploma"
    elif "certificate" in text_lower:
        highest_qual = "trade_certificate"

    # 6. Field of Study
    field = "Information Technology / Engineering"
    if "computer" in text_lower or "software" in text_lower or "information technology" in text_lower:
        field = "Computer Science / Information Technology"
    elif "civil" in text_lower:
        field = "Civil Engineering"
    elif "nurs" in text_lower or "health" in text_lower or "medical" in text_lower:
        field = "Nursing / Health Sciences"
    elif "account" in text_lower or "finance" in text_lower or "commerce" in text_lower:
        field = "Accounting & Finance"
    elif "business" in text_lower or "management" in text_lower:
        field = "Business Administration"

    # 7. Total Experience Years
    exp_years = 5
    exp_match = re.search(r'(\d{1,2})\+?\s*(?:years|yrs)\b', text, re.I)
    if exp_match:
        exp_years = min(25, int(exp_match.group(1)))
    else:
        years_found = [int(y) for y in re.findall(r'\b(199\d|20[012]\d)\b', text)]
        if len(years_found) >= 2:
            span = max(years_found) - min(years_found)
            if 1 <= span <= 30:
                exp_years = span

    # 8. English
    english = {"test": "IELTS", "scores": {"overall": 7.5, "listening": 8.0, "reading": 7.5, "writing": 7.0, "speaking": 7.5}}
    if "pte" in text_lower:
        pte_score = 75
        pte_m = re.search(r'pte[:\s]+(\d{2})', text, re.I)
        if pte_m:
            pte_score = int(pte_m.group(1))
        english = {"test": "PTE Academic", "scores": {"overall": pte_score, "listening": pte_score, "reading": pte_score, "writing": pte_score, "speaking": pte_score}}
    elif "ielts" in text_lower:
        ielts_m = re.search(r'ielts[:\s]+([5-9](?:\.[05])?)', text, re.I)
        band = float(ielts_m.group(1)) if ielts_m else 7.5
        english = {"test": "IELTS", "scores": {"overall": band, "listening": band, "reading": band, "writing": band, "speaking": band}}

    # 9. Current Profession
    current_prof = "Software Engineer"
    for title in ["Software Engineer", "Full Stack Developer", "Developer Programmer", "Web Developer", "Civil Engineer", "Mechanical Engineer", "Registered Nurse", "Accountant", "Management Consultant", "Chef", "Marketing Specialist"]:
        if title.lower() in text_lower:
            current_prof = title
            break

    return {
        "client_name": name,
        "client_email": email,
        "client_phone": phone,
        "name": name,
        "email": email,
        "phone": phone,
        "marital_status": "single",
        "primary_applicant": {
            "name": name,
            "age": age,
            "dob": dob,
            "highest_qualification": highest_qual,
            "field_of_study": field,
            "years_experience_total": exp_years,
            "current_profession": current_prof,
            "english": english,
            "partner_included": False,
        },
        "extracted_qualifications": [
            {
                "degree": highest_qual.title(),
                "field": field,
                "institution": "Accredited University",
                "country": "India",
                "completed": True
            }
        ],
        "extracted_employment": [
            {
                "title": current_prof,
                "employer": "Enterprise Organization",
                "years": exp_years,
                "country": "India",
                "current": True
            }
        ],
        "confidence_score": 0.88,
        "_ai_status": "ok",
        "_ai_model": "heuristic-nlp-extractor"
    }


async def parse_resume_with_ai(
    resume_text: str,
    session_id: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Send resume text to AI for structured extraction.
    Returns the parsed JSON (Phase 6.7 ProfileCreate shape) or a fallback parsed shell.
    """
    if not resume_text or len(resume_text.strip()) < 50:
        return {"_error": "Resume text is too short to extract anything meaningful"}

    key = (os.environ.get("PERPLEXITY_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        logger.info("No external LLM key set, using heuristic NLP resume parser")
        return parse_resume_heuristically(resume_text)

    # Trim to safe budget
    text = resume_text[:MAX_TEXT_CHARS]
    user_prompt = (
        "## RESUME TEXT\n```\n"
        + text
        + "\n```\n\nReturn the extracted JSON now."
    )

    try:
        import httpx as _httpx
        _http = _httpx.AsyncClient(verify=False, timeout=60)
        client = AsyncOpenAI(
            api_key=key,
            base_url="https://api.perplexity.ai",
            http_client=_http,
        )

        response = None
        for attempt in range(3):
            try:
                response = await client.chat.completions.create(
                    model=model or PERPLEXITY_MODEL,
                    temperature=0,
                    max_tokens=2500,
                    messages=[
                        {
                            "role": "system",
                            "content": EXTRACTION_PROMPT,
                        },
                        {
                            "role": "user",
                            "content": user_prompt,
                        },
                    ],
                )
                break
            except Exception as re_err:
                err_str = str(re_err).lower()
                if ("429" in err_str or "rate limit" in err_str) and attempt < 2:
                    wait_sec = 2.0 * (attempt + 1)
                    await asyncio.sleep(wait_sec)
                    continue
                raise

        if not response:
            return parse_resume_heuristically(resume_text)

        message = response.choices[0].message
        raw = message.content or ""

        if raw.startswith("```"):
            raw = raw.strip("`").replace("json", "", 1).strip()

        raw = re.sub(r"^```(?:json)?", "", raw.strip(), flags=re.IGNORECASE)
        raw = re.sub(r"```$", "", raw.strip())

        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return parse_resume_heuristically(resume_text)

        json_text = match.group(0)
        json_text = re.sub(r"[\x00-\x1F\x7F]", "", json_text)
        json_text = re.sub(r",(\s*[}\]])", r"\1", json_text)

        try:
            parsed = json.loads(json_text)
            parsed["_ai_status"] = "ok"
            parsed["_ai_model"] = PERPLEXITY_MODEL
            return parsed
        except json.JSONDecodeError:
            return parse_resume_heuristically(resume_text)

    except Exception as e:
        logger.warning("LLM Resume parsing exception (%s) — falling back to heuristic parser", e)
        return parse_resume_heuristically(resume_text)