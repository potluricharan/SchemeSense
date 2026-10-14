"""OCR extraction pipeline (Phase 2).

Accepts an uploaded scanned/photographed document, pre-processes it with OpenCV,
extracts raw text with Tesseract, then normalises it into a structured
{"field": value} JSON whose keys match the rule-engine field names so the
gap-analysis module can compare extracted values against scheme rules.

Document fields computed here: aadhaar_number, name, dob, age, gender,
annual_income, disability_pct, issue_date, marital_status, certificate_no.
"""
from __future__ import annotations

import io
import logging
import re
from datetime import date

import cv2
import numpy as np
import pytesseract
from PIL import Image

from core import config

log = logging.getLogger(__name__)

_AADHAAR_RE = re.compile(r"\b(\d{4})\s?(\d{4})\s?(\d{4})\b")
_DATE_RE = re.compile(r"\b(\d{1,2})[/\-.]([a-zA-Z]{3}|\d{1,2})[/\-.](\d{2,4})\b")
_AMOUNT_RE = re.compile(r"(?:[\u20b9Rs\.\s]*?)(\d{1,2}(?:,\d{3})+(?:\.\d+)?|\d{3,7}(?:\.\d+)?)\s*(?:per|/-|only)?")
_CURRENCY_AMOUNT_RE = re.compile(r"(?:Rs\.?|INR|rupees|\u20b9)\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)
_PCT_RE = re.compile(r"(\d{1,3})\s*%")
_AGE_RE = re.compile(r"\b(?:age|aged)\s*:?\s*(\d{1,3})\b", re.IGNORECASE)
_HEADER_LINE_RE = re.compile(
    r"government|of india|certificate|income|no\s*[:.]|date|issu|valid|scheme|"
    r"department|sanctioned|the|welfare|district|state|residential",
    re.IGNORECASE,
)


def _ensure_tesseract() -> None:
    pytesseract.pytesseract.tesseract_cmd = config.tesseract_cmd()


def preprocess(image: Image.Image) -> np.ndarray:
    arr = np.array(image.convert("RGB"))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    gray = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh


def image_from_bytes(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


def is_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def extract_pdf(data: bytes, dpi: int = 200) -> dict:
    """Parse a PDF: pull embedded (digital) text page-by-page and OCR any page
    that is a scan (too little embedded text) by rendering it to an image."""
    import fitz  # PyMuPDF

    doc = fitz.open(stream=data, filetype="pdf")
    page_texts = [(p.get_text() or "").strip() for p in doc]
    total_embedded = sum(len(t) for t in page_texts)
    scanned = total_embedded < 12 * len(doc)
    parts = []
    for i, t in enumerate(page_texts):
        if scanned or len(t) < 12:
            pix = doc[i].get_pixmap(dpi=dpi, alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            parts.append(extract_text_from_image(img))
        else:
            parts.append(t)
    return {"text": "\n\n".join(parts), "pages": len(doc), "scanned": scanned}


def preview_image(data: bytes, max_px: int = 900) -> Image.Image:
    """Return a displayable image for a document, rendering a PDF's first page."""
    if is_pdf(data):
        import fitz

        doc = fitz.open(stream=data, filetype="pdf")
        pix = doc[0].get_pixmap(dpi=120, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    else:
        img = image_from_bytes(data)
    if img.width > max_px:
        img.thumbnail((max_px, max_px))
    return img


def extract_text_from_image(image: Image.Image) -> str:
    _ensure_tesseract()
    try:
        processed = preprocess(image)
        text = pytesseract.image_to_string(processed, lang="eng")
        if len(text.strip()) < 12:  # fall back to raw image pass
            text = pytesseract.image_to_string(image, lang="eng")
        return text
    except Exception as exc:  # pragma: no cover
        log.exception("Tesseract failed")
        return f"[OCR error: {exc}]"


# ---- field normalisation -------------------------------------------------
def _first_amount(near_words: list[str]) -> float | None:
    for w in near_words:
        m = re.sub(r"[^\d.,]", "", w)
        if re.match(r"^\d{3,7}(,\d{3})*$", m):
            return float(m.replace(",", ""))
    return None


def _find_near(text_low: str, anchor: str, window: int = 120) -> str:
    idx = text_low.find(anchor)
    if idx == -1:
        return ""
    return text_low[max(0, idx - window // 2): idx + window]


def _find_after(text_low: str, anchor: str, radius: int = 120) -> str:
    """Text starting at the anchor, forward only (for expiry/validity dates so an
    earlier date elsewhere on the page is not picked up)."""
    idx = text_low.find(anchor)
    if idx == -1:
        return ""
    return text_low[idx: idx + radius]


def _parse_date(txt: str):
    m = _DATE_RE.search(txt)
    if not m:
        return None
    d, mo, y = m.group(1), m.group(2), m.group(3)
    try:
        if mo.isalpha():
            return date(int(y), int(mo), int(d))
        return date(int(y), int(mo), int(d))
    except ValueError:
        return None


def normalize_fields(text: str, doc_type: str = "") -> dict:
    if not text or text.startswith("[OCR error"):
        return {"ocr_error": text or "no text"}

    low = text.lower()
    fields: dict = {}

    am = _AADHAAR_RE.search(text)
    if am:
        fields["aadhaar_number"] = am.group(1) + am.group(2) + am.group(3)

    # Name: first meaningful *(non-header)* line
    for line in text.splitlines():
        line = line.strip()
        if 3 < len(line) < 60 and not re.search(r"\d{4,}", line):
            if not _HEADER_LINE_RE.search(line):
                name = re.sub(r"^(name|shri|smt|kumari)\s*[:.]?\s*", "", line, flags=re.IGNORECASE).strip()
                fields.setdefault("name", name)
                break

    # Date of birth: only when explicitly anchored to birth/DOB
    dob_ctx = _find_near(low, "birth")
    if "dob" in low or "birth" in low:
        d = _parse_date(dob_ctx or text)
        if d:
            fields["dob"] = d.isoformat()
            today = date.today()
            fields["age"] = today.year - d.year - ((today.month, today.day) < (d.month, d.day))

    if "male" in low or "man" in low:
        fields["gender"] = "male"
    elif "female" in low or "woman" in low:
        fields["gender"] = "female"

    for kw in ("widow", "widowed"):
        if kw in low:
            fields["marital_status"] = "widowed"
            break

    # income certificate: prefer an explicit Rs./₹/INR amount, else a large
    # comma-grouped figure **after** the "income" keyword
    if "income" in low:
        ctx = _find_near(low, "income")
        m = _CURRENCY_AMOUNT_RE.search(str(ctx))
        if not m:
            m = _CURRENCY_AMOUNT_RE.search(low)
        if m:
            val = float(m.group(1).replace(",", ""))
            if 1000 < val:
                fields["annual_income"] = val
        if "annual_income" not in fields:
            m2 = re.search(r"income.*?(\d{1,2}(?:,\d{3})+|\d{5,7})(?:\.\d+)?", low)
            if m2 and float(m2.group(1).replace(",", "")) > 1000:
                fields["annual_income"] = float(m2.group(1).replace(",", ""))

    # disability
    dis_ctx = _find_near(low, "disab")
    if dis_ctx:
        pm = _PCT_RE.search(dis_ctx)
        if pm:
            fields["disability_pct"] = int(pm.group(1))

    # issue / validity dates
    issue_ctx = _find_near(low, "issu") or _find_near(low, "date of issue")
    idate = _parse_date(issue_ctx)
    if idate:
        fields["issue_date"] = idate.isoformat()

    valid_ctx = _find_after(low, "valid")
    vdate = _parse_date(valid_ctx)
    if vdate:
        fields["valid_till"] = vdate.isoformat()

    if doc_type:
        fields["document_type"] = doc_type

    return fields


def extract_document(data: bytes, doc_type: str = "") -> dict:
    if is_pdf(data):
        pd = extract_pdf(data)
        return {
            "text": pd["text"],
            "fields": normalize_fields(pd["text"], doc_type),
            "format": "pdf",
            "pages": pd["pages"],
        }
    img = image_from_bytes(data)
    text = extract_text_from_image(img)
    return {"text": text, "fields": normalize_fields(text, doc_type), "format": "image"}