from signgate.intent import adversarial_manifest, default_manifest
from signgate.pdf import extract_pdf_terms, generate_agreement_pdf
from signgate.twopass import canonical_from_llm, run_two_pass
from signgate.verify import decide_gate


def _approved_shape():
    return {
        "contract_value_amount": 50000,
        "contract_value_currency": "USD",
        "term_months": 12,
        "payment_terms_days": 30,
        "termination_notice_days": 30,
        "auto_renewal": False,
        "personal_guarantee": False,
        "exclusivity": False,
        "governing_law": "Singapore",
        "customer": "Northstar Analytics",
        "vendor": "Atlas Systems",
        "bank_account": "001-4729183",
        "required_attachments": ["Statement of Work"],
    }


def test_llm_currency_format_canonicalizes_to_integer():
    canonical = canonical_from_llm(
        {
            "contract_value_amount": "$50,000.00",
            "contract_value_currency": "usd",
            "term_months": "12",
            "payment_terms_days": 30,
            "termination_notice_days": 30,
            "auto_renewal": "false",
            "personal_guarantee": "no",
            "exclusivity": False,
            "governing_law": "Singapore",
            "customer": "Northstar Analytics",
            "vendor": "Atlas Systems",
            "bank_account": "001-4729183",
            "required_attachments": ["Statement of Work"],
        }
    )
    assert canonical["contract_value_amount"] == 50000
    assert canonical["contract_value_currency"] == "USD"
    assert canonical["auto_renewal"] is False


def test_python_pass_blocks_when_llm_hallucinates_a_match():
    approved = default_manifest()
    bad, _ = generate_agreement_pdf(adversarial_manifest(approved), adversarial=True)
    extracted = extract_pdf_terms(bad)
    two = run_two_pass(approved, extracted, llm_json=_approved_shape(), llm_used=True)
    assert two["deterministic_winner"] == "python"
    assert any(item["field"] == "contract_value_amount" for item in two["parser_mismatches"])
    assert any(item["field"] == "contract_value_amount" for item in two["llm_parser_conflicts"])
    decision = decide_gate(approved, extracted, two_pass=two, llm_used=True)
    assert decision["status"] == "blocked"
    assert decision["llm_may_not_open_gate"] is True
    fields = [item["field"] for item in decision["discrepancies"]]
    assert "contract_value" in fields
    assert "auto_renewal" in fields


def test_python_pass_blocks_llm_json_that_disagrees_with_manifest():
    approved = default_manifest()
    good, _ = generate_agreement_pdf(approved)
    extracted = extract_pdf_terms(good)
    hallucinated = _approved_shape()
    hallucinated["contract_value_amount"] = 500000
    two = run_two_pass(approved, extracted, llm_json=hallucinated, llm_used=True)
    assert any(item["field"] == "contract_value_amount" for item in two["llm_mismatches"])
    decision = decide_gate(approved, extracted, two_pass=two, llm_used=True)
    assert decision["status"] == "blocked"
