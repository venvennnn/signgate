from __future__ import annotations

import io
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from .pdf import money
from .types import IntentManifest

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def _font(size: int) -> ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _lines(manifest: IntentManifest) -> list[str]:
    value = money(manifest)
    sow = "Statement of Work" in manifest["required_attachments"]
    renewal = (
        f"This Agreement automatically renews for successive {manifest['commercial_terms']['term_months']}-month periods."
        if manifest["legal_terms"]["auto_renewal"]
        else "This Agreement does not automatically renew."
    )
    return [
        manifest["title"].upper(),
        f"Customer: {manifest['parties']['customer']}",
        f"Vendor: {manifest['parties']['vendor']}",
        f"1.1 Contract Value. The total contract value is {value}.",
        f"1.2 Term. This Agreement shall remain in force for {manifest['commercial_terms']['term_months']} months.",
        f"1.3 Payment. Invoices are payable within {manifest['commercial_terms']['payment_terms_days']} days.",
        f"2.1 Either party may terminate by providing {manifest['legal_terms']['termination_notice_days']} days written notice.",
        f"2.2 {renewal}",
        f"3.1 Governing Law. This Agreement is governed by the laws of {manifest['legal_terms']['governing_law']}.",
        "3.2 Liability. Neither party provides a personal guarantee.",
        "3.3 Exclusivity. This Agreement does not grant exclusivity.",
        f"Account number: {manifest['bank_details']['account_number'] or '—'}",
        "Schedule A — Statement of Work. This Statement of Work is attached to and forms part of the Agreement."
        if sow
        else "Required schedules: none.",
        f"Signed by: {manifest['signer']['name']}",
    ]


def _render_page(lines: list[str], seed: int = 7) -> Image.Image:
    rng = random.Random(seed)
    width, height = 1275, 1650
    image = Image.new("RGB", (width, height), (236, 232, 222))
    draw = ImageDraw.Draw(image)
    title_font = _font(36)
    body_font = _font(22)
    y = 90
    draw.text((80, y), lines[0], fill=(28, 26, 22), font=title_font)
    y += 70
    for line in lines[1:]:
        draw.text((80, y), line, fill=(32, 30, 26), font=body_font)
        y += 48
    pixels = image.load()
    for _ in range(18000):
        x = rng.randint(0, width - 1)
        yy = rng.randint(0, height - 1)
        shade = rng.randint(160, 210)
        pixels[x, yy] = (shade, shade - 4, shade - 10)
    image = ImageEnhance.Contrast(image).enhance(1.05)
    image = image.filter(ImageFilter.SMOOTH)
    return image.rotate(rng.uniform(-0.6, 0.6), resample=Image.Resampling.BICUBIC, fillcolor=(236, 232, 222))


def generate_scan_pdf(manifest: IntentManifest, adversarial: bool = True) -> tuple[bytes, str]:
    """Image-only PDF that looks like a phone-scanned contract. Returns (pdf, source_text)."""
    lines = _lines(manifest)
    if adversarial:
        lines.insert(1, "VENDOR MARK-UP — scanned copy returned for signature")
    source_text = "\n".join(lines)
    page = _render_page(lines)
    buf = io.BytesIO()
    page.save(buf, format="JPEG", quality=55)
    buf.seek(0)
    out = io.BytesIO()
    canvas = Canvas(out, pagesize=letter)
    canvas.drawImage(ImageReader(buf), 0, 0, width=letter[0], height=letter[1])
    canvas.save()
    return out.getvalue(), source_text


def image_to_scan_pdf(image_bytes: bytes) -> bytes:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    out = io.BytesIO()
    canvas = Canvas(out, pagesize=letter)
    canvas.drawImage(ImageReader(image), 0, 0, width=letter[0], height=letter[1], preserveAspectRatio=True, anchor="c")
    canvas.save()
    return out.getvalue()
