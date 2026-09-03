from __future__ import annotations

import hashlib
import json
from typing import Any

from .types import ExtractedTerms, IntentManifest


def money_label(amount: int, currency: str) -> str:
    return f"{currency} {amount:,}"


def checksum_from_manifest(manifest: IntentManifest) -> dict[str, Any]:
    return {
        "contract_value": money_label(
            manifest["commercial_terms"]["contract_value"]["amount"],
            manifest["commercial_terms"]["contract_value"]["currency"],
        ),
        "termination_notice": f"{manifest['legal_terms']['termination_notice_days']} days",
        "auto_renewal": manifest["legal_terms"]["auto_renewal"],
        "personal_guarantee": manifest["legal_terms"]["personal_guarantee"],
        "exclusivity": manifest["legal_terms"]["exclusivity"],
        "governing_law": manifest["legal_terms"]["governing_law"],
        "term_months": manifest["commercial_terms"]["term_months"],
        "payment_terms_days": manifest["commercial_terms"]["payment_terms_days"],
        "customer": manifest["parties"]["customer"],
        "vendor": manifest["parties"]["vendor"],
        "required_attachments": sorted(manifest["required_attachments"]),
        "bank_account": manifest["bank_details"]["account_number"],
    }


def checksum_from_extracted(extracted: ExtractedTerms) -> dict[str, Any]:
    value = extracted["commercial_terms"]["contract_value"]
    notice = extracted["legal_terms"]["termination_notice_days"]
    return {
        "contract_value": money_label(value["amount"], value["currency"]) if value else "unextracted",
        "termination_notice": f"{notice} days" if notice is not None else "unextracted",
        "auto_renewal": extracted["legal_terms"]["auto_renewal"] or False,
        "personal_guarantee": extracted["legal_terms"]["personal_guarantee"] or False,
        "exclusivity": extracted["legal_terms"]["exclusivity"] or False,
        "governing_law": extracted["legal_terms"]["governing_law"] or "unextracted",
        "term_months": extracted["commercial_terms"]["term_months"]
        if extracted["commercial_terms"]["term_months"] is not None
        else -1,
        "payment_terms_days": extracted["commercial_terms"]["payment_terms_days"]
        if extracted["commercial_terms"]["payment_terms_days"] is not None
        else -1,
        "customer": extracted["parties"]["customer"] or "unextracted",
        "vendor": extracted["parties"]["vendor"] or "unextracted",
        "required_attachments": sorted(extracted["attachments_found"]),
        "bank_account": extracted["bank_details"]["account_number"],
    }


def fingerprint(checksum: dict[str, Any]) -> str:
    canonical = json.dumps(checksum, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
