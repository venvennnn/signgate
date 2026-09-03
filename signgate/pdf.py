from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas

from .checksum import checksum_from_manifest, fingerprint
from .extract import extract_terms_from_pages
from .types import ExtractedTerms, IntentManifest


def money(manifest: IntentManifest) -> str:
    value = manifest["commercial_terms"]["contract_value"]
    return f"{value['currency']} {value['amount']:,}"


def _fields_block(manifest: IntentManifest) -> str:
    return "\n".join(
        [
            "--- SIGNGATE INTENT FIELDS ---",
            f"document_type: {manifest['document_type']}",
            f"customer: {manifest['parties']['customer']}",
            f"vendor: {manifest['parties']['vendor']}",
            f"contract_value_amount: {manifest['commercial_terms']['contract_value']['amount']}",
            f"contract_value_currency: {manifest['commercial_terms']['contract_value']['currency']}",
            f"term_months: {manifest['commercial_terms']['term_months']}",
            f"payment_terms_days: {manifest['commercial_terms']['payment_terms_days']}",
            f"termination_notice_days: {manifest['legal_terms']['termination_notice_days']}",
            f"auto_renewal: {str(manifest['legal_terms']['auto_renewal']).lower()}",
            f"personal_guarantee: {str(manifest['legal_terms']['personal_guarantee']).lower()}",
            f"exclusivity: {str(manifest['legal_terms']['exclusivity']).lower()}",
            f"governing_law: {manifest['legal_terms']['governing_law']}",
            f"attachments: {', '.join(manifest['required_attachments'])}",
            f"bank_account: {manifest['bank_details']['account_number'] or ''}",
            f"bank_account_name: {manifest['bank_details']['account_name'] or ''}",
            f"bank_name: {manifest['bank_details']['bank_name'] or ''}",
            "--- END SIGNGATE INTENT FIELDS ---",
        ]
    )


def agreement_html(manifest: IntentManifest, adversarial: bool = False) -> str:
    value = money(manifest)
    sow = "Statement of Work" in manifest["required_attachments"]
    renew = (
        f"This Agreement <strong>automatically renews</strong> for successive {manifest['commercial_terms']['term_months']}-month periods unless either party provides {manifest['legal_terms']['termination_notice_days']} days' written notice."
        if manifest["legal_terms"]["auto_renewal"]
        else "This Agreement <strong>does not automatically renew</strong>. Any extension requires a new written instrument signed by both parties."
    )
    guarantee = (
        "The undersigned individual <strong>personally guarantees</strong> the Customer's obligations under this Agreement."
        if manifest["legal_terms"]["personal_guarantee"]
        else "Neither party provides a personal guarantee. No personal liability is assumed by any director, officer, or employee."
    )
    exclusive = (
        "Customer hereby appoints Vendor as its exclusive provider of the Services."
        if manifest["legal_terms"]["exclusivity"]
        else "This Agreement does not grant exclusivity. Customer may obtain similar services from other vendors."
    )
    banner = '<div class="banner">MODIFIED COPY — not the approved instrument.</div>' if adversarial else ""
    sow_html = (
        "<h2>Schedule A — Statement of Work</h2><p>This Statement of Work is attached to and forms part of the Agreement.</p>"
        if sow
        else ""
    )
    return f"""<!doctype html><html><head><meta charset="utf-8" /><title>{manifest['title']}</title></head>
<body>{banner}<h1>{manifest['title'].upper()}</h1>
<p>Customer: {manifest['parties']['customer']}</p>
<p>Vendor: {manifest['parties']['vendor']}</p>
<p>1.1 Contract Value. The total contract value is <strong>{value}</strong>.</p>
<p>1.2 Term. This Agreement shall remain in force for <strong>{manifest['commercial_terms']['term_months']} months</strong>.</p>
<p>1.3 Payment. Invoices are payable within <strong>{manifest['commercial_terms']['payment_terms_days']} days</strong>.</p>
<p>2.1 Either party may terminate this Agreement by providing <strong>{manifest['legal_terms']['termination_notice_days']} days</strong> written notice.</p>
<p>2.2 {renew}</p>
<p>3.1 Governing Law. This Agreement is governed by the laws of <strong>{manifest['legal_terms']['governing_law']}</strong>.</p>
<p>3.2 Liability. {guarantee}</p>
<p>3.3 Exclusivity. {exclusive}</p>
<p>Account name: {manifest['bank_details']['account_name'] or '—'}</p>
<p>Bank: {manifest['bank_details']['bank_name'] or '—'}</p>
<p>Account number: {manifest['bank_details']['account_number'] or '—'}</p>
{sow_html}
<p>Signed by: {manifest['signer']['name']}</p>
<pre>{_fields_block(manifest)}</pre>
</body></html>"""


def generate_agreement_pdf(manifest: IntentManifest, adversarial: bool = False) -> tuple[bytes, int]:
    value = money(manifest)
    include_sow = "Statement of Work" in manifest["required_attachments"]
    buf = BytesIO()
    canvas = Canvas(buf, pagesize=letter)
    width, height = letter
    left = 0.9 * inch

    def header(title: str, subtitle: str) -> float:
        y = height - 0.75 * inch
        canvas.setFillColorRGB(0.11, 0.10, 0.09)
        canvas.setFont("Times-Bold", 16)
        canvas.drawString(left, y, "SIGNGATE")
        canvas.setFillColorRGB(0.54, 0.42, 0.18)
        canvas.setFont("Times-Italic", 9)
        canvas.drawString(left, y - 14, "Authorization integrity copy")
        canvas.setFillColorRGB(0.11, 0.10, 0.09)
        canvas.setFont("Times-Bold", 15)
        canvas.drawCentredString(width / 2, y - 40, title)
        canvas.setFont("Times-Roman", 10)
        canvas.setFillColorRGB(0.27, 0.27, 0.27)
        canvas.drawCentredString(width / 2, y - 56, subtitle)
        canvas.setStrokeColorRGB(0.78, 0.63, 0.36)
        canvas.line(left, y - 70, width - left, y - 70)
        return y - 96

    def footer(page: int, total: int) -> None:
        canvas.setFont("Times-Italic", 8)
        canvas.setFillColorRGB(0.47, 0.47, 0.47)
        canvas.drawCentredString(
            width / 2,
            0.55 * inch,
            f"Page {page} of {total}  ·  Not legally binding until a human signs after SignGate verification.",
        )

    def write_lines(y: float, lines: list[str], size: int = 11) -> float:
        canvas.setFillColorRGB(0.11, 0.10, 0.09)
        canvas.setFont("Times-Roman", size)
        for line in lines:
            for wrapped in _wrap(line, 92):
                canvas.drawString(left, y, wrapped)
                y -= 16
            y -= 4
        return y

    total_pages = 4 if include_sow else 3
    subtitle = "Modified copy — not the approved instrument" if adversarial else "Prepared from an approved Intent Manifest"
    y = header(manifest["title"].upper(), subtitle)
    canvas.setFont("Times-Bold", 12)
    canvas.setFillColorRGB(0.11, 0.10, 0.09)
    canvas.drawString(left, y, "Parties")
    y = write_lines(
        y - 20,
        [
            f"Customer: {manifest['parties']['customer']}",
            f"Vendor: {manifest['parties']['vendor']}",
            "1. Commercial terms",
            f"1.1 Contract Value. The total contract value is {value}.",
            f"1.2 Term. This Agreement shall remain in force for {manifest['commercial_terms']['term_months']} months from the Effective Date.",
            f"1.3 Payment. Vendor shall invoice monthly. Invoices are payable within {manifest['commercial_terms']['payment_terms_days']} days.",
            f"1.4 Services. Vendor shall provide {manifest['commercial_terms']['services_description']} as further described in any attached schedules.",
        ],
    )
    footer(1, total_pages)
    canvas.showPage()

    y = header(manifest["title"].upper(), "Legal terms")
    canvas.setFont("Times-Bold", 12)
    canvas.drawString(left, y, "2. Termination and renewal")
    renew = (
        f"2.2 This Agreement automatically renews for successive {manifest['commercial_terms']['term_months']}-month periods unless either party provides {manifest['legal_terms']['termination_notice_days']} days written notice of non-renewal."
        if manifest["legal_terms"]["auto_renewal"]
        else "2.2 This Agreement does not automatically renew. Any extension requires a new written instrument signed by both parties."
    )
    guarantee = (
        "3.2 Personal Guarantee. The undersigned individual personally guarantees the Customer's obligations under this Agreement."
        if manifest["legal_terms"]["personal_guarantee"]
        else "3.2 Liability. Neither party provides a personal guarantee. No personal liability is assumed by any director, officer, or employee."
    )
    exclusive = (
        "3.3 Exclusivity. Customer hereby appoints Vendor as its exclusive provider of the Services."
        if manifest["legal_terms"]["exclusivity"]
        else "3.3 Exclusivity. This Agreement does not grant exclusivity. Customer may obtain similar services from other vendors."
    )
    y = write_lines(
        y - 20,
        [
            f"2.1 Either party may terminate this Agreement by providing {manifest['legal_terms']['termination_notice_days']} days written notice to the other party.",
            renew,
            "3. Governing law and liability",
            f"3.1 Governing Law. This Agreement is governed by the laws of {manifest['legal_terms']['governing_law']}, without regard to conflict-of-law principles.",
            guarantee,
            exclusive,
            "4. Payment destination",
            f"Account name: {manifest['bank_details']['account_name'] or '—'}",
            f"Bank: {manifest['bank_details']['bank_name'] or '—'}",
            f"Account number: {manifest['bank_details']['account_number'] or '—'}",
        ],
    )
    footer(2, total_pages)
    canvas.showPage()

    page_no = 3
    if include_sow:
        y = header("Schedule A — Statement of Work", "Required attachment")
        write_lines(
            y,
            [
                "This Statement of Work is attached to and forms part of the Agreement.",
                f"Vendor will deliver {manifest['commercial_terms']['services_description']} for {manifest['parties']['customer']}.",
                "Deliverables include a production data pipeline, operational documentation, and a named technical contact.",
                f"Fees under this Statement of Work are included in the contract value of {value}.",
            ],
        )
        footer(page_no, total_pages)
        canvas.showPage()
        page_no += 1

    y = header("Signature block", "Human authorization required")
    y = write_lines(
        y,
        [
            "This document may be prepared by an agent. It becomes legally real only when a human signs after SignGate verification.",
            f"Signed by: {manifest['signer']['name']}",
            f"Title: {manifest['signer']['title']}",
            f"Email: {manifest['signer']['email']}",
            "Signature: ________________________________",
            "Date: ________________________________",
        ],
    )
    canvas.setFont("Courier", 8)
    for line in _fields_block(manifest).splitlines():
        canvas.drawString(left, y, line)
        y -= 11
    footer(page_no, total_pages)
    canvas.save()
    return buf.getvalue(), total_pages


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if len(trial) > width and current:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines or [""]


def extract_pdf_terms(data: bytes) -> ExtractedTerms:
    reader = PdfReader(BytesIO(data))
    pages = [(page.extract_text() or "").replace("\x00", " ") for page in reader.pages]
    return extract_terms_from_pages(pages or [""])


def merge_pdfs(*blobs: bytes) -> bytes:
    writer = PdfWriter()
    for blob in blobs:
        reader = PdfReader(BytesIO(blob))
        for page in reader.pages:
            writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def pdf_page_count(data: bytes) -> int:
    return len(PdfReader(BytesIO(data)).pages)


def has_cover_sheet(data: bytes) -> bool:
    first = (PdfReader(BytesIO(data)).pages[0].extract_text() or "") if data else ""
    return "SIGNGATE VERIFICATION CERTIFICATE" in first.upper() or "VERIFICATION CERTIFICATE" in first.upper()


def cover_sheet_html(manifest: IntentManifest, verified_at: str | None = None) -> str:
    checksum = fingerprint(checksum_from_manifest(manifest))
    stamp = verified_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    value = money(manifest)
    sow = "Statement of Work" in manifest["required_attachments"]
    renewal = "No automatic renewal" if not manifest["legal_terms"]["auto_renewal"] else "Automatic renewal"
    return f"""<!doctype html><html><head><meta charset="utf-8"/><title>SignGate Verification Certificate</title>
<style>
  body {{ font-family: Georgia, serif; color: #1b1a16; padding: 48px; }}
  .mark {{ width: 96px; height: 96px; border-radius: 999px; border: 8px solid #0b7a4b; color: #0b7a4b;
           display: flex; align-items: center; justify-content: center; font-size: 54px; font-weight: 700; }}
  h1 {{ letter-spacing: .12em; font-size: 18px; }}
  .hash {{ font-family: ui-monospace, monospace; font-size: 12px; word-break: break-all; }}
  li {{ margin: 8px 0; }}
</style></head><body>
<div class="mark">✓</div>
<h1>SIGNGATE VERIFICATION CERTIFICATE</h1>
<p>The final PDF matches the approved Intent Manifest. The Signature Gate is OPEN.</p>
<p class="hash">Intent Manifest hash: {checksum}</p>
<p>Verified at {stamp}</p>
<ol>
  <li>Contract value: <strong>{value}</strong></li>
  <li>Term: <strong>{manifest['commercial_terms']['term_months']} months</strong></li>
  <li>Termination notice: <strong>{manifest['legal_terms']['termination_notice_days']}-day termination</strong></li>
  <li>Automatic renewal: <strong>{renewal}</strong></li>
  <li>Required attachment: <strong>{"Statement of Work required" if sow else "None"}</strong></li>
</ol>
<p>{manifest['parties']['customer']} · {manifest['parties']['vendor']}</p>
<p>This certificate is merged in front of the instrument immediately before the Foxit eSign handoff.</p>
</body></html>"""


def generate_cover_sheet(manifest: IntentManifest, verified_at: str | None = None) -> bytes:
    checksum = fingerprint(checksum_from_manifest(manifest))
    stamp = verified_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    value = money(manifest)
    sow = "Statement of Work" in manifest["required_attachments"]
    buf = BytesIO()
    canvas = Canvas(buf, pagesize=letter)
    width, height = letter
    canvas.setFillColorRGB(0.043, 0.478, 0.294)
    canvas.circle(width / 2, height - 1.35 * inch, 0.55 * inch, fill=1, stroke=0)
    canvas.setFillColorRGB(1, 1, 1)
    canvas.setFont("Times-Bold", 36)
    canvas.drawCentredString(width / 2, height - 1.48 * inch, "✓")
    canvas.setFillColorRGB(0.043, 0.478, 0.294)
    canvas.setFont("Times-Bold", 16)
    canvas.drawCentredString(width / 2, height - 2.15 * inch, "SIGNGATE VERIFICATION CERTIFICATE")
    canvas.setFillColorRGB(0.11, 0.10, 0.09)
    canvas.setFont("Times-Roman", 12)
    canvas.drawCentredString(
        width / 2,
        height - 2.45 * inch,
        "The final PDF matches the approved Intent Manifest. The Signature Gate is OPEN.",
    )
    canvas.setFont("Courier", 8)
    canvas.drawCentredString(width / 2, height - 2.75 * inch, f"Intent Manifest hash: {checksum}")
    canvas.setFont("Times-Italic", 10)
    canvas.drawCentredString(width / 2, height - 3.0 * inch, f"Verified at {stamp}")
    terms = [
        f"1.  Contract value: {value}",
        f"2.  Term: {manifest['commercial_terms']['term_months']} months",
        f"3.  Termination notice: {manifest['legal_terms']['termination_notice_days']}-day termination",
        f"4.  Automatic renewal: {'No automatic renewal' if not manifest['legal_terms']['auto_renewal'] else 'Automatic renewal'}",
        f"5.  Required attachment: {'Statement of Work required' if sow else 'None'}",
    ]
    y = height - 3.55 * inch
    canvas.setFont("Times-Roman", 13)
    canvas.setFillColorRGB(0.11, 0.10, 0.09)
    for line in terms:
        canvas.drawString(1.3 * inch, y, line)
        y -= 28
    y -= 16
    canvas.setFont("Times-Roman", 11)
    canvas.drawString(1.3 * inch, y, f"Customer: {manifest['parties']['customer']}")
    canvas.drawString(1.3 * inch, y - 18, f"Vendor: {manifest['parties']['vendor']}")
    canvas.setFont("Times-Italic", 9)
    canvas.setFillColorRGB(0.4, 0.4, 0.4)
    canvas.drawCentredString(
        width / 2,
        0.7 * inch,
        "Merged in front of the instrument immediately before the Foxit eSign handoff.",
    )
    canvas.save()
    return buf.getvalue()


def generate_receipt_pdf(document_id: str, title: str, gate: str, checksum: str, actor: str, findings: list[str]) -> bytes:
    buf = BytesIO()
    canvas = Canvas(buf, pagesize=letter)
    y = 740
    canvas.setFont("Times-Bold", 18)
    canvas.drawString(64, y, "SignGate audit receipt")
    canvas.setFont("Times-Roman", 11)
    for line in [
        document_id,
        f"Document: {title}",
        f"Gate: {gate.upper()}",
        f"Semantic checksum: {checksum}",
        f"Actor: {actor}",
    ]:
        y -= 18
        canvas.drawString(64, y, line)
    y -= 28
    canvas.setFont("Times-Bold", 12)
    canvas.drawString(64, y, "Findings")
    canvas.setFont("Times-Roman", 11)
    if not findings:
        y -= 18
        canvas.drawString(64, y, "No material or critical discrepancies.")
    for finding in findings:
        y -= 16
        canvas.drawString(64, y, f"• {finding[:110]}")
    canvas.save()
    return buf.getvalue()
