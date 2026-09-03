from __future__ import annotations

import re
from typing import Any

from .checksum import money_label
from .types import Discrepancy, ExtractedTerms, IntentManifest, TwoPassResult

CANONICAL_FIELDS = (
    "contract_value_amount",
    "contract_value_currency",
    "term_months",
    "payment_terms_days",
    "termination_notice_days",
    "auto_renewal",
    "personal_guarantee",
    "exclusivity",
    "governing_law",
    "customer",
    "vendor",
    "bank_account",
    "required_attachments",
)


def _norm_name(value: str | None) -> str:
    if not value:
        return ""
    text = value.lower()
    text = re.sub(r"pte\.?\s*ltd\.?", "", text)
    text = re.sub(r"inc\.?|llc|ltd\.?|limited|corp\.?|corporation", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).replace(",", "").replace("$", "").strip()
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        return None
    return int(float(match.group(1)))


def _as_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "yes", "1", "on"}:
        return True
    if text in {"false", "no", "0", "off"}:
        return False
    return None


def _as_currency(value: Any) -> str | None:
    if not value:
        return None
    token = str(value).upper().replace("US$", "USD").replace("$", "USD").strip()
    if token in {"USD", "SGD", "EUR", "GBP"}:
        return token
    return token[:3] if len(token) >= 3 else token


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def canonical_from_manifest(manifest: IntentManifest) -> dict[str, Any]:
    return {
        "contract_value_amount": int(manifest["commercial_terms"]["contract_value"]["amount"]),
        "contract_value_currency": manifest["commercial_terms"]["contract_value"]["currency"].upper(),
        "term_months": int(manifest["commercial_terms"]["term_months"]),
        "payment_terms_days": int(manifest["commercial_terms"]["payment_terms_days"]),
        "termination_notice_days": int(manifest["legal_terms"]["termination_notice_days"]),
        "auto_renewal": bool(manifest["legal_terms"]["auto_renewal"]),
        "personal_guarantee": bool(manifest["legal_terms"]["personal_guarantee"]),
        "exclusivity": bool(manifest["legal_terms"]["exclusivity"]),
        "governing_law": (manifest["legal_terms"]["governing_law"] or "").strip(),
        "customer": manifest["parties"]["customer"],
        "vendor": manifest["parties"]["vendor"],
        "bank_account": (manifest["bank_details"]["account_number"] or "").replace(" ", ""),
        "required_attachments": sorted(manifest["required_attachments"]),
    }


def canonical_from_extracted(extracted: ExtractedTerms) -> dict[str, Any]:
    value = extracted["commercial_terms"]["contract_value"]
    return {
        "contract_value_amount": int(value["amount"]) if value else None,
        "contract_value_currency": (value["currency"].upper() if value else None),
        "term_months": extracted["commercial_terms"]["term_months"],
        "payment_terms_days": extracted["commercial_terms"]["payment_terms_days"],
        "termination_notice_days": extracted["legal_terms"]["termination_notice_days"],
        "auto_renewal": extracted["legal_terms"]["auto_renewal"],
        "personal_guarantee": extracted["legal_terms"]["personal_guarantee"],
        "exclusivity": extracted["legal_terms"]["exclusivity"],
        "governing_law": (extracted["legal_terms"]["governing_law"] or None),
        "customer": extracted["parties"]["customer"],
        "vendor": extracted["parties"]["vendor"],
        "bank_account": (extracted["bank_details"]["account_number"] or None),
        "required_attachments": sorted(extracted["attachments_found"]),
    }


def canonical_from_llm(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not raw:
        return None
    nested_value = raw.get("contract_value") if isinstance(raw.get("contract_value"), dict) else {}
    amount = raw.get("contract_value_amount")
    if amount is None:
        amount = nested_value.get("amount") if nested_value else raw.get("contract_value")
    currency = raw.get("contract_value_currency")
    if currency is None:
        currency = nested_value.get("currency") if nested_value else None
    commercial = raw.get("commercial_terms") if isinstance(raw.get("commercial_terms"), dict) else {}
    legal = raw.get("legal_terms") if isinstance(raw.get("legal_terms"), dict) else {}
    parties = raw.get("parties") if isinstance(raw.get("parties"), dict) else {}
    bank = raw.get("bank_details") if isinstance(raw.get("bank_details"), dict) else {}
    attachments = raw.get("required_attachments") or raw.get("attachments") or raw.get("attachments_found")
    return {
        "contract_value_amount": _as_int(amount if amount is not None else commercial.get("contract_value")),
        "contract_value_currency": _as_currency(currency or commercial.get("currency") or "USD"),
        "term_months": _as_int(raw.get("term_months", commercial.get("term_months"))),
        "payment_terms_days": _as_int(raw.get("payment_terms_days", commercial.get("payment_terms_days"))),
        "termination_notice_days": _as_int(
            raw.get("termination_notice_days", legal.get("termination_notice_days"))
        ),
        "auto_renewal": _as_bool(raw.get("auto_renewal", legal.get("auto_renewal"))),
        "personal_guarantee": _as_bool(raw.get("personal_guarantee", legal.get("personal_guarantee"))),
        "exclusivity": _as_bool(raw.get("exclusivity", legal.get("exclusivity"))),
        "governing_law": (raw.get("governing_law") or legal.get("governing_law") or None),
        "customer": raw.get("customer") or parties.get("customer"),
        "vendor": raw.get("vendor") or parties.get("vendor"),
        "bank_account": raw.get("bank_account") or bank.get("account_number"),
        "required_attachments": sorted(_as_list(attachments)),
    }


def _values_equal(field: str, approved: Any, found: Any) -> bool:
    if found is None:
        return False
    if field in {"customer", "vendor", "governing_law"}:
        return _norm_name(str(approved)) == _norm_name(str(found))
    if field == "bank_account":
        return str(approved or "").replace(" ", "") == str(found or "").replace(" ", "")
    if field == "required_attachments":
        return sorted(x.lower() for x in (approved or [])) == sorted(x.lower() for x in (found or []))
    if field == "contract_value_currency":
        return str(approved).upper() == str(found).upper()
    return approved == found


def _label(field: str, value: Any) -> str:
    if value is None:
        return "Not found"
    if field == "contract_value_amount":
        return f"{int(value):,}"
    if field == "auto_renewal":
        return "Yes" if value else "No"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        return ", ".join(value) or "(none)"
    return str(value)


def diff_canonical(approved: dict[str, Any], found: dict[str, Any] | None, source: str) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    if found is None:
        return [
            {
                "field": "llm_json",
                "source": source,
                "approved": "schema JSON",
                "found": "unavailable",
            }
        ]
    for field in CANONICAL_FIELDS:
        left = approved.get(field)
        right = found.get(field)
        if field == "required_attachments" and not left:
            continue
        if field in {"customer", "vendor"} and not right:
            continue
        if field == "bank_account" and not left:
            continue
        if not _values_equal(field, left, right):
            mismatches.append(
                {
                    "field": field,
                    "source": source,
                    "approved": left,
                    "found": right,
                }
            )
    return mismatches


def mismatches_to_findings(mismatches: list[dict[str, Any]], layer: str = "syntax") -> list[Discrepancy]:
    findings: list[Discrepancy] = []
    for item in mismatches:
        field = item["field"]
        severity = "critical" if field in {
            "contract_value_amount",
            "contract_value_currency",
            "governing_law",
            "customer",
            "vendor",
            "bank_account",
            "personal_guarantee",
        } else "material"
        findings.append(
            {
                "id": f"{layer}-{field}",
                "severity": severity,  # type: ignore[typeddict-item]
                "layer": "exact" if layer == "syntax" else "semantic",  # type: ignore[typeddict-item]
                "field": "contract_value" if field.startswith("contract_value") else field,
                "title": f"Deterministic mismatch: {field}",
                "approved_value": _label(field, item["approved"]),
                "found_value": _label(field, item["found"]),
                "page": None,
                "excerpt": None,
                "rationale": (
                    "Python compared canonical JSON field-for-field. "
                    f"{field}: approved {_label(field, item['approved'])} != found {_label(field, item['found'])}."
                ),
                "confidence": 1.0,
            }
        )
    return findings


def run_two_pass(
    manifest: IntentManifest,
    extracted: ExtractedTerms,
    llm_json: dict[str, Any] | None = None,
    llm_used: bool = False,
) -> TwoPassResult:
    approved = canonical_from_manifest(manifest)
    parser_json = canonical_from_extracted(extracted)
    llm_canonical = canonical_from_llm(llm_json) if llm_used else None
    parser_mismatches = diff_canonical(approved, parser_json, "parser")
    llm_mismatches = diff_canonical(approved, llm_canonical, "llm") if llm_used else []
    conflicts: list[dict[str, Any]] = []
    if llm_used and llm_canonical is not None:
        for field in CANONICAL_FIELDS:
            parser_value = parser_json.get(field)
            llm_value = llm_canonical.get(field)
            if parser_value is None or llm_value is None:
                continue
            if not _values_equal(field, parser_value, llm_value):
                conflicts.append(
                    {
                        "field": field,
                        "parser": parser_value,
                        "llm": llm_value,
                        "note": "LLM JSON disagrees with Foxit/parser JSON. Deterministic parser wins.",
                    }
                )
    return {
        "parser_json": parser_json,
        "llm_json": llm_canonical,
        "llm_raw": llm_json,
        "llm_used": llm_used,
        "llm_may_not_open_gate": True,
        "deterministic_winner": "python",
        "parser_mismatches": parser_mismatches,
        "llm_mismatches": llm_mismatches,
        "llm_parser_conflicts": conflicts,
        "approved_json": approved,
    }


def money_from_canonical(canonical: dict[str, Any]) -> str:
    amount = canonical.get("contract_value_amount")
    currency = canonical.get("contract_value_currency") or "USD"
    if amount is None:
        return "—"
    return money_label(int(amount), str(currency))
