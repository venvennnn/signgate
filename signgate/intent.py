from __future__ import annotations

import copy
import re
from typing import Literal

from .types import IntentManifest

CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}
WORD_MONTHS = {"one": 12, "a": 12, "two": 24, "three": 36}

DEFAULT_PROMPT = (
    "Create a one-year data-services agreement for $50,000, "
    "with 30-day termination and no automatic renewal."
)


def default_manifest() -> IntentManifest:
    return {
        "document_type": "vendor_agreement",
        "title": "Data Services Agreement",
        "parties": {"customer": "Northstar Analytics", "vendor": "Atlas Systems"},
        "commercial_terms": {
            "contract_value": {"amount": 50_000, "currency": "USD"},
            "term_months": 12,
            "payment_terms_days": 30,
            "services_description": "data processing, analytics pipeline, and related professional services",
        },
        "legal_terms": {
            "termination_notice_days": 30,
            "auto_renewal": False,
            "governing_law": "Singapore",
            "personal_guarantee": False,
            "exclusivity": False,
        },
        "required_attachments": ["Statement of Work"],
        "must_not_include": ["Exclusivity", "Automatic renewal", "Personal liability"],
        "bank_details": {
            "account_name": "Atlas Systems Pte. Ltd.",
            "account_number": "001-4729183",
            "bank_name": "DBS Bank",
        },
        "signer": {
            "name": "Priya Menon",
            "email": "priya.menon@northstar.example",
            "title": "Head of Legal Operations",
        },
    }


def adversarial_manifest(base: IntentManifest) -> IntentManifest:
    tampered = copy.deepcopy(base)
    tampered["commercial_terms"]["contract_value"] = {
        "amount": base["commercial_terms"]["contract_value"]["amount"] * 10,
        "currency": base["commercial_terms"]["contract_value"]["currency"],
    }
    tampered["legal_terms"]["termination_notice_days"] = 90
    tampered["legal_terms"]["auto_renewal"] = True
    tampered["legal_terms"]["personal_guarantee"] = False
    tampered["required_attachments"] = []
    tampered["must_not_include"] = []
    return tampered


def _detect_currency(prompt: str, amount_match: str) -> str:
    around = prompt.lower()
    if re.search(r"\bsgd\b|singapore dollar", around):
        return "SGD"
    if re.search(r"\beur\b|euro", around):
        return "EUR"
    if re.search(r"\bgbp\b|pound", around):
        return "GBP"
    symbol = amount_match.strip()[:1]
    return CURRENCY_SYMBOLS.get(symbol, "USD")


def _extract_party(prompt: str, role: Literal["vendor", "customer"]) -> str | None:
    patterns = (
        [
            r"(?:with|vendor|supplier|provider)\s+([A-Z][A-Za-z0-9&.\- ]{2,40}?)(?:\s+for|\s+at|\s*,|\s*\.|$)",
            r"(?:and)\s+([A-Z][A-Za-z0-9&.\- ]{2,40}?)\s+(?:as )?(?:the )?vendor",
        ]
        if role == "vendor"
        else [
            r"(?:customer|client|buyer)\s+([A-Z][A-Za-z0-9&.\- ]{2,40}?)(?:\s+and|\s+with|\s*,|\s*\.|$)",
            r"(?:for)\s+([A-Z][A-Za-z0-9&.\- ]{2,40}?)\s+(?:as )?(?:the )?customer",
        ]
    )
    for pattern in patterns:
        match = re.search(pattern, prompt)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()
    return None


def extract_intent(prompt: str) -> IntentManifest:
    manifest = default_manifest()
    text = prompt.strip() or DEFAULT_PROMPT
    lower = text.lower()

    money = re.search(r"(?:USD|SGD|EUR|GBP|US\$|S\$|\$|€|£)\s*([\d,]+(?:\.\d{1,2})?)", text, re.I)
    if not money:
        money = re.search(r"([\d,]+(?:\.\d{1,2})?)\s*(?:USD|dollars)", text, re.I)
    if money:
        amount = float(money.group(1).replace(",", ""))
        if amount > 0:
            manifest["commercial_terms"]["contract_value"] = {
                "amount": int(amount),
                "currency": _detect_currency(text, money.group(0)),
            }

    months = re.search(r"(\d+)\s*[-\s]?month", lower)
    years = re.search(r"(\d+)\s*[-\s]?year", lower) or re.search(r"\b(one|a|two|three)[-\s]year", lower)
    if months:
        manifest["commercial_terms"]["term_months"] = int(months.group(1))
    elif years:
        token = years.group(1)
        manifest["commercial_terms"]["term_months"] = WORD_MONTHS.get(token, int(token) * 12 if token.isdigit() else 12)

    notice = re.search(
        r"(\d+)[-\s]?day(?:s)?(?:\s+(?:written\s+)?)?(?:termination|notice|cancel)",
        lower,
    ) or re.search(r"(?:terminat\w+|cancel\w+|notice).{0,24}(\d+)[-\s]?day", lower)
    if notice:
        manifest["legal_terms"]["termination_notice_days"] = int(notice.group(1))

    payment = re.search(r"(\d+)[-\s]?day(?:s)?\s+(?:payment|net)", lower) or re.search(r"net\s*(\d+)", lower)
    if payment:
        manifest["commercial_terms"]["payment_terms_days"] = int(payment.group(1))

    if re.search(r"\bno(?:t)?\s+(?:automatic(?:ally)?\s+)?renew", lower) or re.search(
        r"without\s+auto(?:matic)?[-\s]?renew", lower
    ):
        manifest["legal_terms"]["auto_renewal"] = False
        if "Automatic renewal" not in manifest["must_not_include"]:
            manifest["must_not_include"].append("Automatic renewal")
    elif re.search(r"auto(?:matic(?:ally)?)?\s+renew", lower):
        manifest["legal_terms"]["auto_renewal"] = True
        manifest["must_not_include"] = [item for item in manifest["must_not_include"] if item != "Automatic renewal"]

    if re.search(r"personal(?:ly)?\s+(?:guarantee|liable|liability)", lower):
        manifest["legal_terms"]["personal_guarantee"] = not bool(
            re.search(r"no\s+personal(?:ly)?\s+(?:guarantee|liab)", lower)
        )

    if re.search(r"\bexclusiv", lower):
        manifest["legal_terms"]["exclusivity"] = not bool(re.search(r"\bno(?:t)?\s+exclusiv", lower))

    law = re.search(
        r"(?:governed by|governing law(?:\s+of)?|under(?: the)? laws of)\s+([A-Z][A-Za-z ]{2,40}?)(?:\.|,|$)",
        text,
        re.I,
    )
    if law:
        manifest["legal_terms"]["governing_law"] = law.group(1).strip()
    elif "singapore" in lower:
        manifest["legal_terms"]["governing_law"] = "Singapore"

    vendor = _extract_party(text, "vendor")
    customer = _extract_party(text, "customer")
    if vendor:
        manifest["parties"]["vendor"] = vendor
    if customer:
        manifest["parties"]["customer"] = customer

    if re.search(r"statement of work|sow", lower) and "Statement of Work" not in manifest["required_attachments"]:
        manifest["required_attachments"].append("Statement of Work")

    if re.search(r"data[-\s]?services?", lower):
        manifest["title"] = "Data Services Agreement"
        manifest["commercial_terms"]["services_description"] = (
            "data processing, analytics pipeline, and related professional services"
        )
    elif "vendor" in lower:
        manifest["title"] = "Vendor Agreement"

    email = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)
    if email:
        manifest["signer"]["email"] = email.group(0)

    return manifest
