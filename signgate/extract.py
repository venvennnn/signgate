from __future__ import annotations

import re
from typing import Any

from .types import ExtractedTerms, Money


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _page_of(pages: list[str], pattern: str) -> dict[str, Any] | None:
    compiled = re.compile(pattern, re.I)
    for i, page in enumerate(pages):
        match = compiled.search(page)
        if match:
            idx = match.start()
            excerpt = _collapse(page[max(0, idx - 40) : idx + len(match.group(0)) + 80])
            captured = (match.group(1) if match.lastindex else "").strip()
            return {
                "page": i + 1,
                "excerpt": excerpt,
                "matched": match.group(0),
                "value": captured or None,
            }
    return None


def _find_labeled(pages: list[str], label: str) -> dict[str, Any] | None:
    return _page_of(pages, rf"{label}[:\s]+([^\n]{{2,80}})")


def _parse_money(raw: str) -> Money | None:
    match = re.search(r"(USD|SGD|EUR|GBP|US\$|S\$|\$)\s*([\d,]+(?:\.\d{1,2})?)", raw, re.I)
    if not match:
        match = re.search(r"([\d,]+(?:\.\d{1,2})?)\s*(USD|dollars)", raw, re.I)
    if not match:
        return None
    amount = float((match.group(2) if match.lastindex and match.lastindex >= 2 else match.group(1)).replace(",", ""))
    token = (match.group(1) or "USD").upper()
    currency = "USD" if token in {"$", "US$", "DOLLARS"} else token.replace("$", "")
    return {"amount": int(amount), "currency": currency or "USD"}


def _parse_days(raw: str | None) -> int | None:
    if not raw:
        return None
    match = re.search(r"(\d+)\s*day", raw, re.I)
    return int(match.group(1)) if match else None


def _parse_months(raw: str | None) -> int | None:
    if not raw:
        return None
    months = re.search(r"(\d+)\s*month", raw, re.I)
    if months:
        return int(months.group(1))
    years = re.search(r"(\d+)\s*year", raw, re.I)
    if years:
        return int(years.group(1)) * 12
    if re.search(r"one[-\s]year|twelve months", raw, re.I):
        return 12
    return None


def _polarity(text: str, positive: str, negative: str) -> bool | None:
    lower = text.lower()
    if re.search(negative, lower, re.I):
        return False
    if re.search(positive, lower, re.I):
        return True
    return None


def _machine_block(pages: list[str]) -> dict[str, str] | None:
    joined = "\n".join(pages)
    block = re.search(
        r"--- SIGNGATE INTENT FIELDS ---([\s\S]*?)--- END SIGNGATE INTENT FIELDS ---",
        joined,
    )
    if not block:
        return None
    fields: dict[str, str] = {}
    for line in block.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def _bool_field(value: str | None) -> bool | None:
    if value is None:
        return None
    if value.lower() in {"true", "yes", "1"}:
        return True
    if value.lower() in {"false", "no", "0"}:
        return False
    return None


def extract_terms_from_pages(pages: list[str]) -> ExtractedTerms:
    joined = "\n\n".join(pages)
    machine = _machine_block(pages) or {}
    field_pages: dict[str, int | None] = {}
    excerpts: dict[str, str] = {}

    def remember(field: str, hit: dict[str, Any] | None) -> None:
        if not hit:
            return
        field_pages[field] = hit["page"]
        excerpts[field] = hit["excerpt"]

    contract_hit = _page_of(
        pages,
        r"(?:contract value|total (?:contract )?value|fees payable)[^\n]{0,40}((?:USD|SGD|EUR|GBP|\$)\s*[\d,]+)",
    ) or _page_of(pages, r"(?:USD|\$)\s*[\d,]{3,}")
    remember("contract_value", contract_hit)

    term_hit = _page_of(
        pages, r"(?:term of (?:this )?agreement|shall remain in force for|duration)[^\n]{0,40}"
    ) or _page_of(pages, r"\b\d+\s*months?\b")
    remember("term_months", term_hit)

    pay_hit = _page_of(pages, r"(?:payable within|payment terms|net)\s*\d+\s*days")
    remember("payment_terms_days", pay_hit)

    term_notice_hit = _page_of(
        pages,
        r"(?:terminat\w+|written notice)[^\n]{0,80}\d+\s*days|\d+\s*days[^\n]{0,40}(?:written )?notice",
    )
    remember("termination_notice_days", term_notice_hit)

    remember(
        "auto_renewal",
        _page_of(pages, r"does not automatically renew|no automatic renewal|automatically renews?")
        or _page_of(pages, r"renewal"),
    )
    remember("governing_law", _page_of(pages, r"governed by the laws of [A-Za-z ]+|governing law[^\n]{0,40}"))
    remember("personal_guarantee", _page_of(pages, r"personal(?:ly)?\s+(?:guarantee|liable|liability)"))
    remember("exclusivity", _page_of(pages, r"exclusiv(?:e|ity)"))

    customer_hit = _find_labeled(pages, "Customer") or _page_of(pages, r"Customer[:\s]+([A-Z][^\n]{2,60})")
    vendor_hit = _find_labeled(pages, "Vendor") or _page_of(pages, r"Vendor[:\s]+([A-Z][^\n]{2,60})")
    remember("customer", customer_hit)
    remember("vendor", vendor_hit)
    remember("bank_account", _page_of(pages, r"account(?: number)?[:\s]+[0-9-]+"))

    contract_value = None
    if machine.get("contract_value_amount"):
        contract_value = {
            "amount": int(float(machine["contract_value_amount"])),
            "currency": machine.get("contract_value_currency") or "USD",
        }
    elif contract_hit:
        contract_value = _parse_money(contract_hit["excerpt"])

    remain = re.search(r"remain in force for ([^\n.]+)", joined, re.I)
    payable = re.search(r"payable within ([^\n.]+)", joined, re.I)
    term_months = (
        int(machine["term_months"])
        if machine.get("term_months")
        else _parse_months((term_hit or {}).get("matched") or (term_hit or {}).get("excerpt") or (remain.group(1) if remain else None))
    )
    payment_terms_days = (
        int(machine["payment_terms_days"])
        if machine.get("payment_terms_days")
        else _parse_days((pay_hit or {}).get("matched") or (pay_hit or {}).get("excerpt") or (payable.group(0) if payable else None))
    )
    termination_notice_days = (
        int(machine["termination_notice_days"])
        if machine.get("termination_notice_days")
        else _parse_days((term_notice_hit or {}).get("matched") or (term_notice_hit or {}).get("excerpt"))
    )

    auto_renewal = _bool_field(machine.get("auto_renewal"))
    if auto_renewal is None:
        auto_renewal = _polarity(
            joined,
            r"automatically renews?(?:\s+for)?",
            r"does not automatically renew|no automatic renewal|shall not automatically renew|without automatic renewal",
        )
    personal_guarantee = _bool_field(machine.get("personal_guarantee"))
    if personal_guarantee is None:
        personal_guarantee = _polarity(
            joined,
            r"personal(?:ly)?\s+(?:guarantees?|liable|liability)(?!\s+is not)",
            r"no personal(?:ly)?\s+(?:guarantee|liability)|does not (?:provide|include) a personal guarantee|neither party provides a personal guarantee",
        )
    exclusivity = _bool_field(machine.get("exclusivity"))
    if exclusivity is None:
        exclusivity = _polarity(
            joined,
            r"exclusive(?:ly)?(?:\s+vendor|\s+supplier|\s+provider)?|exclusivity",
            r"no exclusivity|not exclusive|non-exclusive|does not grant exclusivity",
        )

    governing_law = machine.get("governing_law")
    if not governing_law:
        law = re.search(r"governed by the laws of ([A-Za-z ]{2,40}?)(?:\.|,|;|\n)", joined, re.I)
        governing_law = law.group(1).strip() if law else None

    def clean_party(value: str) -> str:
        value = re.sub(r"\s+\d+(\.\d+)?\s.*$", "", value)
        value = re.sub(r"\s+(Customer|Vendor|Contract|Account)\b.*$", "", value, flags=re.I)
        return value.strip()

    customer = machine.get("customer")
    if not customer and customer_hit:
        raw = customer_hit.get("value") or re.sub(r"^.*?Customer[:\s]+", "", customer_hit["matched"], flags=re.I)
        customer = clean_party(re.split(r"[.\n]", raw)[0])
    vendor = machine.get("vendor")
    if not vendor and vendor_hit:
        raw = vendor_hit.get("value") or re.sub(r"^.*?Vendor[:\s]+", "", vendor_hit["matched"], flags=re.I)
        vendor = clean_party(re.split(r"[.\n]", raw)[0])

    attachments: list[str] = []
    if re.search(r"statement of work", joined, re.I) or "statement of work" in machine.get("attachments", "").lower():
        attachments.append("Statement of Work")
    if re.search(r"service level agreement|\bSLA\b", joined):
        attachments.append("Service Level Agreement")

    account = machine.get("bank_account") or (
        m.group(1) if (m := re.search(r"account(?: number)?[:\s]+([0-9-]+)", joined, re.I)) else None
    )
    account_name = machine.get("bank_account_name") or (
        m.group(1).strip() if (m := re.search(r"account name[:\s]+([^\n]+)", joined, re.I)) else None
    )
    bank_name = machine.get("bank_name") or (
        m.group(1).strip() if (m := re.search(r"bank[:\s]+([A-Za-z0-9 .]+)", joined, re.I)) else None
    )

    return {
        "parties": {"customer": customer, "vendor": vendor},
        "commercial_terms": {
            "contract_value": contract_value,
            "term_months": term_months if isinstance(term_months, int) else None,
            "payment_terms_days": payment_terms_days if isinstance(payment_terms_days, int) else None,
        },
        "legal_terms": {
            "termination_notice_days": termination_notice_days
            if isinstance(termination_notice_days, int)
            else None,
            "auto_renewal": auto_renewal,
            "governing_law": governing_law,
            "personal_guarantee": personal_guarantee,
            "exclusivity": exclusivity,
        },
        "attachments_found": attachments,
        "bank_details": {
            "account_name": account_name,
            "account_number": account,
            "bank_name": bank_name,
        },
        "signer_names": [m.group(1).strip() for m in re.finditer(r"Signed by[:\s]+([A-Z][^\n]{2,60})", joined)],
        "page_count": len(pages),
        "field_pages": field_pages,
        "excerpts": excerpts,
        "raw_text": joined,
    }
