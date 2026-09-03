from pypdf import PdfReader
from io import BytesIO

from signgate.intent import default_manifest
from signgate.pdf import generate_agreement_pdf, generate_cover_sheet, has_cover_sheet, merge_pdfs, pdf_page_count


def test_cover_sheet_is_page_one_after_merge():
    manifest = default_manifest()
    agreement, pages = generate_agreement_pdf(manifest)
    cover = generate_cover_sheet(manifest, "2026-09-03 12:00 UTC")
    compiled = merge_pdfs(cover, agreement)
    assert has_cover_sheet(compiled)
    assert pdf_page_count(compiled) == pages + 1
    first = PdfReader(BytesIO(compiled)).pages[0].extract_text()
    assert "SIGNGATE VERIFICATION CERTIFICATE" in first
    assert "50,000" in first.replace(" ", "") or "50000" in first.replace(",", "") or "50,000" in first
    assert "30-day termination" in first
    assert "No automatic renewal" in first
    checksum_line = [line for line in first.splitlines() if "hash" in line.lower()]
    assert checksum_line
