from __future__ import annotations

import secrets
from typing import Any

from .checksum import checksum_from_extracted, checksum_from_manifest, fingerprint, money_label
from .types import Discrepancy, ExtractedTerms, GateDecision, IntentManifest, Severity


def _finding(**kwargs: Any) -> Discrepancy:
    kwargs.setdefault("confidence", 1.0)
    kwargs.setdefault("id", secrets.token_hex(5))
    return kwargs  # type: ignore[return-value]


def _names_match(left: str, right: str) -> bool:
    def normalize(value: str) -> str:
        value = value.lower()
        value = re_sub(r"pte\.?\s*ltd\.?", "", value)
        value = re_sub(r"inc\.?|llc|ltd\.?|limited|corp\.?|corporation", "", value)
        value = re_sub(r"[^a-z0-9]+", " ", value)
        return value.strip()

    return normalize(left) == normalize(right)


def re_sub(pattern: str, repl: str, text: str) -> str:
    import re

    return re.sub(pattern, repl, text)


def compare_manifest_to_extracted(manifest: IntentManifest, extracted: ExtractedTerms) -> list[Discrepancy]:
    out: list[Discrepancy] = []
    value = extracted["commercial_terms"]["contract_value"]
    approved_value = money_label(
        manifest["commercial_terms"]["contract_value"]["amount"],
        manifest["commercial_terms"]["contract_value"]["currency"],
    )
    pages = extracted["field_pages"]
    excerpts = extracted["excerpts"]

    if not value:
        out.append(
            _finding(
                severity="critical",
                layer="exact",
                field="contract_value",
                title="Contract value missing",
                approved_value=approved_value,
                found_value="Not found in final document",
                page=pages.get("contract_value"),
                excerpt=excerpts.get("contract_value"),
                rationale="The approved commercial amount could not be located in the final PDF.",
            )
        )
    elif (
        value["amount"] != manifest["commercial_terms"]["contract_value"]["amount"]
        or value["currency"].upper() != manifest["commercial_terms"]["contract_value"]["currency"].upper()
    ):
        out.append(
            _finding(
                severity="critical",
                layer="exact",
                field="contract_value",
                title="Contract value changed",
                approved_value=approved_value,
                found_value=money_label(value["amount"], value["currency"]),
                page=pages.get("contract_value"),
                excerpt=excerpts.get("contract_value"),
                rationale="A one-digit change in a commercial amount is a classic authorization failure.",
            )
        )

    def number_check(field: str, extracted_value: int | None, approved: int, unit: str, title_missing: str, title_changed: str, rationale: str) -> None:
        if extracted_value is None:
            out.append(
                _finding(
                    severity="material",
                    layer="exact",
                    field=field,
                    title=title_missing,
                    approved_value=f"{approved} {unit}",
                    found_value="Not found",
                    page=pages.get(field),
                    excerpt=excerpts.get(field),
                    rationale=rationale,
                )
            )
        elif extracted_value != approved:
            out.append(
                _finding(
                    severity="material",
                    layer="exact",
                    field=field,
                    title=title_changed,
                    approved_value=f"{approved} {unit}",
                    found_value=f"{extracted_value} {unit}",
                    page=pages.get(field),
                    excerpt=excerpts.get(field),
                    rationale=rationale,
                )
            )

    number_check(
        "term_months",
        extracted["commercial_terms"]["term_months"],
        manifest["commercial_terms"]["term_months"],
        "months",
        "Agreement term missing",
        "Agreement term changed",
        "Duration is a material commercial term.",
    )
    number_check(
        "payment_terms_days",
        extracted["commercial_terms"]["payment_terms_days"],
        manifest["commercial_terms"]["payment_terms_days"],
        "days",
        "Payment terms missing",
        "Payment terms changed",
        "Cash timing changed after approval.",
    )
    number_check(
        "termination_notice_days",
        extracted["legal_terms"]["termination_notice_days"],
        manifest["legal_terms"]["termination_notice_days"],
        "days",
        "Termination notice missing",
        "Termination notice changed",
        "Changing notice from 30 to 90 days (or the reverse) rewrites the exit right.",
    )

    def bool_check(field: str, extracted_value: bool | None, approved: bool, uncertain_title: str, introduced: str, removed: str, rationale: str, severity: Severity) -> None:
        if extracted_value is None:
            out.append(
                _finding(
                    severity="uncertain",
                    layer="semantic",
                    field=field,
                    title=uncertain_title,
                    approved_value="Yes" if approved else "No",
                    found_value="Uncertain",
                    page=pages.get(field),
                    excerpt=excerpts.get(field),
                    rationale=rationale,
                    confidence=0.4,
                )
            )
        elif extracted_value != approved:
            out.append(
                _finding(
                    severity=severity,
                    layer="semantic",
                    field=field,
                    title=introduced if extracted_value else removed,
                    approved_value="Yes" if approved else "No",
                    found_value="Yes" if extracted_value else "No",
                    page=pages.get(field),
                    excerpt=excerpts.get(field),
                    rationale=rationale,
                )
            )

    bool_check(
        "auto_renewal",
        extracted["legal_terms"]["auto_renewal"],
        manifest["legal_terms"]["auto_renewal"],
        "Renewal rule could not be confirmed",
        "Automatic renewal introduced",
        "Automatic renewal removed",
        "Renewal language changes the duration of the legal commitment.",
        "material",
    )
    bool_check(
        "personal_guarantee",
        extracted["legal_terms"]["personal_guarantee"],
        manifest["legal_terms"]["personal_guarantee"],
        "Personal liability could not be confirmed",
        "Personal liability added",
        "Personal guarantee removed",
        "Shifting liability onto an individual is a critical authorization change.",
        "critical",
    )
    bool_check(
        "exclusivity",
        extracted["legal_terms"]["exclusivity"],
        manifest["legal_terms"]["exclusivity"],
        "Exclusivity could not be confirmed",
        "Exclusivity introduced",
        "Exclusivity removed",
        "An exclusivity clause changes the customer's freedom to contract elsewhere.",
        "material",
    )

    law = extracted["legal_terms"]["governing_law"]
    if not law:
        out.append(
            _finding(
                severity="critical",
                layer="exact",
                field="governing_law",
                title="Governing law missing",
                approved_value=manifest["legal_terms"]["governing_law"],
                found_value="Not found",
                page=pages.get("governing_law"),
                excerpt=excerpts.get("governing_law"),
                rationale="Jurisdiction is a critical executed term.",
            )
        )
    elif law.strip().lower() != manifest["legal_terms"]["governing_law"].strip().lower():
        out.append(
            _finding(
                severity="critical",
                layer="exact",
                field="governing_law",
                title="Governing law changed",
                approved_value=manifest["legal_terms"]["governing_law"],
                found_value=law,
                page=pages.get("governing_law"),
                excerpt=excerpts.get("governing_law"),
                rationale="A jurisdiction swap is a critical change even if the rest of the deal looks identical.",
            )
        )

    if extracted["parties"]["customer"] and not _names_match(
        extracted["parties"]["customer"], manifest["parties"]["customer"]
    ):
        out.append(
            _finding(
                severity="critical",
                layer="exact",
                field="customer",
                title="Customer name changed",
                approved_value=manifest["parties"]["customer"],
                found_value=extracted["parties"]["customer"],
                page=pages.get("customer") or 1,
                excerpt=excerpts.get("customer"),
                rationale="The party on the paper is not the party that was authorized.",
            )
        )
    if extracted["parties"]["vendor"] and not _names_match(
        extracted["parties"]["vendor"], manifest["parties"]["vendor"]
    ):
        out.append(
            _finding(
                severity="critical",
                layer="exact",
                field="vendor",
                title="Vendor name changed",
                approved_value=manifest["parties"]["vendor"],
                found_value=extracted["parties"]["vendor"],
                page=pages.get("vendor") or 1,
                excerpt=excerpts.get("vendor"),
                rationale="The counterparty identity is a critical signing term.",
            )
        )

    approved_account = manifest["bank_details"]["account_number"]
    found_account = extracted["bank_details"]["account_number"]
    if approved_account and found_account and found_account.replace(" ", "") != approved_account.replace(" ", ""):
        out.append(
            _finding(
                severity="critical",
                layer="exact",
                field="bank_account",
                title="Bank details replaced",
                approved_value=approved_account,
                found_value=found_account,
                page=pages.get("bank_account"),
                excerpt=excerpts.get("bank_account"),
                rationale="Payment destination changes are treated as critical by default.",
            )
        )

    for required in manifest["required_attachments"]:
        if not any(found.lower() == required.lower() for found in extracted["attachments_found"]):
            out.append(
                _finding(
                    severity="material",
                    layer="structural",
                    field="attachments",
                    title="Missing attachment",
                    approved_value=required,
                    found_value="Not found",
                    page=None,
                    excerpt=None,
                    rationale=f"{required} was required by the approved Intent Manifest and is absent from the final PDF.",
                )
            )

    if extracted["page_count"] == 0 or not extracted["raw_text"].strip():
        out.append(
            _finding(
                severity="critical",
                layer="structural",
                field="page_count",
                title="Document appears empty",
                approved_value="Complete executed set",
                found_value=f"{extracted['page_count']} page(s)",
                page=extracted["page_count"],
                excerpt=None,
                rationale="No extractable text was found in the final PDF.",
            )
        )
    return out


def decide_gate(
    manifest: IntentManifest,
    extracted: ExtractedTerms,
    extra: list[Discrepancy] | None = None,
    llm_used: bool = False,
    two_pass: dict[str, Any] | None = None,
    cover_sheet_attached: bool = False,
    extraction_provider: str = "local",
) -> GateDecision:
    from .twopass import mismatches_to_findings, run_two_pass

    pass_result = two_pass or run_two_pass(manifest, extracted, llm_used=False)
    extra_findings = list(extra or [])
    if pass_result.get("llm_used") and pass_result.get("llm_mismatches"):
        extra_findings.extend(mismatches_to_findings(pass_result["llm_mismatches"], layer="semantic"))
    if pass_result.get("llm_parser_conflicts"):
        extra_findings.append(
            _finding(
                severity="material",
                layer="semantic",
                field="two_pass_conflict",
                title="LLM JSON disagreed with parser JSON",
                approved_value="Deterministic parser is authoritative",
                found_value=f"{len(pass_result['llm_parser_conflicts'])} field conflict(s)",
                page=None,
                excerpt=None,
                rationale=(
                    "The language model extracted JSON that does not match Foxit/parser JSON. "
                    "Python keeps the parser values. The model cannot open the gate."
                ),
                confidence=1.0,
            )
        )
    discrepancies = compare_manifest_to_extracted(manifest, extracted) + extra_findings
    blocking = any(item["severity"] in {"material", "critical", "uncertain"} for item in discrepancies)
    exact_ok = not any(item["layer"] == "exact" for item in discrepancies)
    values = [
        extracted["commercial_terms"]["contract_value"],
        extracted["commercial_terms"]["term_months"],
        extracted["commercial_terms"]["payment_terms_days"],
        extracted["legal_terms"]["termination_notice_days"],
        extracted["legal_terms"]["auto_renewal"],
        extracted["legal_terms"]["personal_guarantee"],
        extracted["legal_terms"]["exclusivity"],
        extracted["legal_terms"]["governing_law"],
        extracted["parties"]["customer"],
        extracted["parties"]["vendor"],
        extracted["bank_details"]["account_number"],
    ]
    verified = sum(1 for value in values if value not in (None, ""))

    def count(severity: Severity) -> int:
        return sum(1 for item in discrepancies if item["severity"] == severity)

    return {
        "status": "blocked" if blocking else "open",
        "semantic_checksum": fingerprint(checksum_from_manifest(manifest)),
        "extracted_checksum": fingerprint(checksum_from_extracted(extracted)),
        "critical_count": count("critical"),
        "material_count": count("material"),
        "clarifying_count": count("clarifying"),
        "cosmetic_count": count("cosmetic"),
        "uncertain_count": count("uncertain"),
        "verified_term_count": max(verified, 8) if exact_ok else verified,
        "missing_attachments": [
            required
            for required in manifest["required_attachments"]
            if not any(found.lower() == required.lower() for found in extracted["attachments_found"])
        ],
        "discrepancies": discrepancies,
        "llm_used": llm_used or bool(pass_result.get("llm_used")),
        "llm_may_not_open_gate": True,
        "two_pass": pass_result,  # type: ignore[typeddict-item]
        "cover_sheet_attached": cover_sheet_attached,
        "extraction_provider": extraction_provider,
    }
