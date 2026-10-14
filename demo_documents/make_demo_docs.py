"""Generate demo documents for the demo MP family (Ramesh Sharma et al.).

These are real files you can drag into the Document Gap Analysis uploader.
Digital PDFs carry a text layer (parsed directly); the PNG is a "scan" that
exercises the Tesseract OCR path.

Run:  python demo_documents/make_demo_docs.py
"""
from __future__ import annotations

import io
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent

BODY = {
    16: ("Bold", 300),
    13: ("Regular", 338),
}


def _pdf_pages(pages: list[str], size=(620, 420)) -> bytes:
    doc = fitz.open()
    for lines in pages:
        page = doc.new_page(width=size[0], height=size[1])
        y = 70
        for line in lines:
            font = "helv" if ":" not in line[:5] else "hebo"
            page.insert_text((55, y), line, fontname=font, fontsize=12)
            y += 24
    out = io.BytesIO()
    doc.save(out)
    doc.close()
    return out.getvalue()


def _scanned_png(lines: list[str], size=(1400, 900)) -> bytes:
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("arial.ttf", 34)
        font_bold = ImageFont.truetype("arialbd.ttf", 34)
    except Exception:
        font = font_bold = None
    img = Image.new("RGB", size, "white")
    dr = ImageDraw.Draw(img)
    y = 90
    for i, line in enumerate(lines):
        dr.text((70, y), line, fill="black", font=(font_bold if i == 0 else font))
        y += 80
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def main() -> None:
    OUT.mkdir(exist_ok=True)

    aadhaar = _pdf_pages([[
        "Government of India  Unique Identification Authority of India",
        "AADHAAR CARD",
        "Name: Ramesh Sharma",
        "Father's Name: Sukhdev Sharma",
        "Date of Birth: 01/05/1961",
        "Gender: Male",
        "Aadhaar Number: 3456 7890 1234",
        "Address: Village Dhamnod, Khargone District, Madhya Pradesh",
    ]])
    (OUT / "01_aadhaar_ramesh.pdf").write_bytes(aadhaar)

    income = _pdf_pages([[
        "Government of Madhya Pradesh  Revenue Department",
        "INCOME CERTIFICATE",
        "Certificate No: INC/MP/2023/1128",
        "Name: Ramesh Sharma",
        "Annual Family Income: Rs. 72,000 per year",
        "Date of Issue: 12/03/2023",
        "Valid Till: 31/03/2025",
        "Signed: Tehsildar, Khargone District",
    ]])
    (OUT / "02_income_certificate.pdf").write_bytes(income)

    bpl_ration = _pdf_pages([[
        "Government of Madhya Pradesh  Food, Civil Supplies & Consumer Protection Dept",
        "RATION CARD  (Below Poverty Line - BPL)",
        "Card Number: MP/09/2021/4401",
        "Head of Family: Ramesh Sharma",
        "Household: 4 members",
        "Category: Below Poverty Line (BPL)",
        "Public Distribution System (PDS) Ration Card",
    ]])
    (OUT / "03_bpl_ration_card.pdf").write_bytes(bpl_ration)

    obc_caste = _pdf_pages([[
        "Government of Madhya Pradesh  Social Justice Department",
        "CASTE CERTIFICATE",
        "Certificate No: CASTE/MP/2022/8876",
        "Name: Arjun Sharma  (Minor)",
        "Father's Name: Ramesh Sharma",
        "Caste: Other Backward Class (OBC)",
        "Community: Sahu   Category: OBC",
        "Residence: Village Dhamnod, Khargone",
    ]])
    (OUT / "04_obc_caste_certificate.pdf").write_bytes(obc_caste)

    samagra = _pdf_pages([[
        "Government of Madhya Pradesh  Samagra Portal",
        "SAMAGRA FAMILY ID CARD",
        "Samagra ID: 27-0011-2-0345678",
        "Head of Family: Ramesh Sharma",
        "Family Members: 4",
        "Household Socio-Economic Data recorded",
        "Registered Mobile: 9876543210 (Verified)",
    ]])
    (OUT / "05_samagra_id.pdf").write_bytes(samagra)

    income_scan = _scanned_png([
        "Government of Madhya Pradesh  Revenue Department",
        "INCOME CERTIFICATE",
        "Certificate No: INC/MP/2023/1129",
        "Name: Ramesh Sharma",
        "Annual Family Income: Rs. 72,000 per year",
        "Date of Issue: 12/03/2023",
    ])
    (OUT / "06_income_certificate_scan.png").write_bytes(income_scan)

    for f in sorted(OUT.iterdir()):
        if f.suffix in (".pdf", ".png"):
            print(f"{f.name:45s} {f.stat().st_size:7d} bytes")


if __name__ == "__main__":
    main()