from signgate.extract import extract_terms_from_pages
from signgate.intent import adversarial_manifest, default_manifest
from signgate.pdf import extract_pdf_terms, generate_agreement_pdf
from signgate.verify import decide_gate

APPROVED = """DATA SERVICES AGREEMENT
Customer: Northstar Analytics
Vendor: Atlas Systems
1.1 Contract Value. The total contract value is USD 50,000.
1.2 Term. This Agreement shall remain in force for 12 months.
1.3 Payment. Invoices are payable within 30 days.
2.1 Either party may terminate this Agreement by providing 30 days written notice.
2.2 This Agreement does not automatically renew.
3.1 Governing Law. This Agreement is governed by the laws of Singapore.
3.2 Liability. Neither party provides a personal guarantee. No personal liability is assumed by any director.
3.3 Exclusivity. This Agreement does not grant exclusivity.
Account name: Atlas Systems Pte. Ltd.
Bank: DBS Bank
Account number: 001-4729183
Schedule A — Statement of Work
This Statement of Work is attached to and forms part of the Agreement."""


def test_gate_opens_when_document_matches():
    decision = decide_gate(default_manifest(), extract_terms_from_pages([APPROVED]))
    assert decision["status"] == "open"
    assert decision["critical_count"] == 0
    assert decision["material_count"] == 0
    assert decision["missing_attachments"] == []
    assert decision["llm_may_not_open_gate"] is True


def test_blocks_killer_demo_adversarial_edit():
    extracted = extract_terms_from_pages(
        [
            """DATA SERVICES AGREEMENT
Customer: Northstar Analytics
Vendor: Atlas Systems
Contract Value. The total contract value is USD 500,000.
Term. This Agreement shall remain in force for 12 months.
Payment. Invoices are payable within 30 days.
Either party may terminate this Agreement by providing 90 days written notice.
This Agreement automatically renews for successive 12-month periods unless either party provides 90 days written notice.
Governing Law. This Agreement is governed by the laws of Singapore.
Neither party provides a personal guarantee.
This Agreement does not grant exclusivity.
Account number: 001-4729183"""
        ]
    )
    decision = decide_gate(default_manifest(), extracted)
    fields = [item["field"] for item in decision["discrepancies"]]
    assert decision["status"] == "blocked"
    assert "contract_value" in fields
    assert "termination_notice_days" in fields
    assert "auto_renewal" in fields
    assert "attachments" in fields
    value = next(item for item in decision["discrepancies"] if item["field"] == "contract_value")
    assert value["severity"] == "critical"
    assert "50,000" in value["approved_value"]
    assert "500,000" in value["found_value"]


def test_governing_law_and_bank_are_critical():
    extracted = extract_terms_from_pages(
        [APPROVED.replace("Singapore", "Delaware").replace("001-4729183", "999-0001112")]
    )
    decision = decide_gate(default_manifest(), extracted)
    assert decision["status"] == "blocked"
    assert any(item["field"] == "governing_law" and item["severity"] == "critical" for item in decision["discrepancies"])
    assert any(item["field"] == "bank_account" and item["severity"] == "critical" for item in decision["discrepancies"])


def test_personal_liability_blocks():
    extracted = extract_terms_from_pages(
        [
            APPROVED.replace(
                "Neither party provides a personal guarantee. No personal liability is assumed by any director.",
                "The undersigned individual personally guarantees the Customer's obligations under this Agreement.",
            )
        ]
    )
    decision = decide_gate(default_manifest(), extracted)
    assert any(item["field"] == "personal_guarantee" for item in decision["discrepancies"])
    assert decision["status"] == "blocked"


def test_pdf_round_trip():
    approved = default_manifest()
    good, _ = generate_agreement_pdf(approved)
    open_decision = decide_gate(approved, extract_pdf_terms(good))
    assert open_decision["status"] == "open"
    assert "Statement of Work" in extract_pdf_terms(good)["attachments_found"]

    bad, _ = generate_agreement_pdf(adversarial_manifest(approved), adversarial=True)
    bad_terms = extract_pdf_terms(bad)
    blocked = decide_gate(approved, bad_terms)
    assert blocked["status"] == "blocked"
    assert bad_terms["commercial_terms"]["contract_value"]["amount"] == 500000
    assert bad_terms["legal_terms"]["auto_renewal"] is True
    assert "Statement of Work" not in bad_terms["attachments_found"]
