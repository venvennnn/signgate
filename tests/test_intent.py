from signgate.intent import extract_intent


def test_killer_demo_request():
    manifest = extract_intent(
        "Create a one-year data-services agreement for $50,000, with 30-day termination and no automatic renewal."
    )
    assert manifest["document_type"] == "vendor_agreement"
    assert manifest["commercial_terms"]["contract_value"] == {"amount": 50000, "currency": "USD"}
    assert manifest["commercial_terms"]["term_months"] == 12
    assert manifest["legal_terms"]["termination_notice_days"] == 30
    assert manifest["legal_terms"]["auto_renewal"] is False
    assert manifest["legal_terms"]["governing_law"] == "Singapore"
    assert "Statement of Work" in manifest["required_attachments"]
    assert set(manifest["must_not_include"]) >= {"Automatic renewal", "Personal liability", "Exclusivity"}


def test_named_parties_and_renewal():
    manifest = extract_intent(
        "12-month vendor agreement with Helios Cloud for Northstar Analytics as the customer, "
        "SGD 120,000, governed by the laws of England, automatic renewal, 15-day termination."
    )
    assert "Helios Cloud" in manifest["parties"]["vendor"]
    assert manifest["commercial_terms"]["contract_value"] == {"amount": 120000, "currency": "SGD"}
    assert manifest["legal_terms"]["auto_renewal"] is True
    assert manifest["legal_terms"]["termination_notice_days"] == 15
    assert "England" in manifest["legal_terms"]["governing_law"]
