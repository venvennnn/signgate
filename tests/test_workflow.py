import pytest

from signgate import db
from signgate.pdf import has_cover_sheet
from signgate.workflow import (
    approve_manifest,
    create_document,
    generate_document,
    introduce_adversary,
    introduce_scanned_adversary,
    pdf_bytes,
    request_signature,
    restore_approved,
)


def test_open_block_restore_esign(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNGATE_DATA_DIR", str(tmp_path))
    db.reset_connection()

    created = create_document(
        "Create a one-year data-services agreement for $50,000, with 30-day termination and no automatic renewal."
    )
    document_id = created["document"]["id"]
    approve_manifest(document_id, "human:judge")
    opened = generate_document(document_id, "human:judge")
    assert opened["decision"]["status"] == "open"
    assert opened["decision"]["critical_count"] == 0
    assert has_cover_sheet(pdf_bytes(document_id))
    assert opened["current_version"]["source"] == "compiled"

    blocked = introduce_adversary(document_id, "human:judge")
    assert blocked["decision"]["status"] == "blocked"
    fields = [item["field"] for item in blocked["decision"]["discrepancies"]]
    assert {"contract_value", "auto_renewal", "attachments"} <= set(fields)

    with pytest.raises(ValueError, match="BLOCKED"):
        request_signature(document_id, "human:judge")

    restored = restore_approved(document_id, "human:judge")
    assert restored["decision"]["status"] == "open"
    assert has_cover_sheet(pdf_bytes(document_id))
    handed = request_signature(document_id, "human:judge")
    assert handed["signature_request"]["status"] == "prepared"
    assert handed["document"]["status"] == "sent_for_signature"
    tools = {step["tool"] for step in handed["pipeline"]}
    assert {"generate", "cover_sheet", "merge", "esign", "two_pass"} <= tools


def test_scanned_sabotage_blocks_then_revert_opens(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNGATE_DATA_DIR", str(tmp_path))
    db.reset_connection()

    created = create_document(
        "Create a one-year data-services agreement for $50,000, with 30-day termination and no automatic renewal."
    )
    document_id = created["document"]["id"]
    approve_manifest(document_id, "human:judge")
    generate_document(document_id, "human:judge")

    blocked = introduce_scanned_adversary(document_id, "human:judge")
    assert blocked["decision"]["status"] == "blocked"
    fields = [item["field"] for item in blocked["decision"]["discrepancies"]]
    assert "contract_value" in fields
    assert "auto_renewal" in fields
    assert "vendor" not in fields
    ocr_steps = [step for step in blocked["pipeline"] if step["tool"] == "ocr"]
    assert ocr_steps
    assert ocr_steps[-1]["provider"] in {"foxit", "local"}
    if ocr_steps[-1]["provider"] == "local":
        assert ocr_steps[-1]["status"] == "fallback"

    with pytest.raises(ValueError, match="BLOCKED"):
        request_signature(document_id, "human:judge")

    restored = restore_approved(document_id, "human:judge")
    assert restored["decision"]["status"] == "open"
    assert has_cover_sheet(pdf_bytes(document_id))

