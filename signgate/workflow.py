from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .checksum import checksum_from_manifest, fingerprint
from .db import connect, files_dir
from .docx_template import agreement_template, agreement_values, cover_sheet_template, cover_sheet_values
from .extract import extract_terms_from_pages
from .foxit import (
    foxit_combine,
    foxit_configured,
    foxit_create_envelope,
    foxit_generate_document,
    foxit_html_to_pdf,
    foxit_ocr,
    foxit_pdf_to_text,
)
from .intent import adversarial_manifest, extract_intent
from .pdf import (
    agreement_html,
    cover_sheet_html,
    extract_pdf_terms,
    generate_agreement_pdf,
    generate_cover_sheet,
    generate_receipt_pdf,
    has_cover_sheet,
    merge_pdfs,
    pdf_page_count,
)
from .scan import generate_scan_pdf, image_to_scan_pdf
from .semantic import extract_llm_json
from .twopass import run_two_pass
from .verify import decide_gate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(n: int = 10) -> str:
    return secrets.token_urlsafe(n)[: n + 2]


def _conn():
    return connect()


def write_audit(document_id: str, actor: str, action: str, **kwargs: Any) -> None:
    conn = _conn()
    conn.execute(
        """INSERT INTO audit_events
           (id, document_id, actor, timestamp, document_hash, manifest_version, action, previous_state, new_state, reason, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            _id(12),
            document_id,
            actor,
            _now(),
            kwargs.get("document_hash"),
            kwargs.get("manifest_version"),
            action,
            kwargs.get("previous_state"),
            kwargs.get("new_state"),
            kwargs.get("reason"),
            json.dumps(kwargs["metadata"]) if kwargs.get("metadata") is not None else None,
        ),
    )
    conn.commit()


def record_pipeline(
    document_id: str,
    tool: str,
    provider: str,
    status: str,
    detail: str,
    foxit_operation: str | None = None,
) -> None:
    conn = _conn()
    row = conn.execute(
        "SELECT COALESCE(MAX(seq), 0) AS seq FROM pipeline_steps WHERE document_id = ?",
        (document_id,),
    ).fetchone()
    seq = int(row["seq"]) + 1
    conn.execute(
        """INSERT INTO pipeline_steps
           (id, document_id, seq, tool, foxit_operation, provider, status, detail, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (_id(12), document_id, seq, tool, foxit_operation, provider, status, detail, _now()),
    )
    conn.commit()


def _document(document_id: str) -> dict[str, Any]:
    row = _conn().execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if not row:
        raise ValueError("Document not found")
    return dict(row)


def _set_status(document_id: str, status: str) -> None:
    _conn().execute("UPDATE documents SET status = ?, updated_at = ? WHERE id = ?", (status, _now(), document_id))
    _conn().commit()


def _latest_manifest(document_id: str) -> dict[str, Any] | None:
    row = _conn().execute(
        "SELECT * FROM intent_manifests WHERE document_id = ? ORDER BY version DESC LIMIT 1",
        (document_id,),
    ).fetchone()
    if not row:
        return None
    data = dict(row)
    data["payload"] = json.loads(data["payload"])
    return data


def _approved_manifest(document_id: str) -> dict[str, Any] | None:
    row = _conn().execute(
        "SELECT * FROM intent_manifests WHERE document_id = ? AND status = 'approved' ORDER BY version DESC LIMIT 1",
        (document_id,),
    ).fetchone()
    if not row:
        return None
    data = dict(row)
    data["payload"] = json.loads(data["payload"])
    return data


def _current_version(document_id: str) -> dict[str, Any] | None:
    row = _conn().execute(
        "SELECT * FROM document_versions WHERE document_id = ? AND is_current = 1",
        (document_id,),
    ).fetchone()
    return dict(row) if row else None


def get_session(document_id: str) -> dict[str, Any]:
    conn = _conn()
    document = _document(document_id)
    version = _current_version(document_id)
    versions = [dict(r) for r in conn.execute("SELECT * FROM document_versions WHERE document_id = ? ORDER BY version", (document_id,))]
    extracted = None
    if version:
        row = conn.execute(
            "SELECT payload FROM extracted_terms WHERE version_id = ? ORDER BY created_at DESC LIMIT 1",
            (version["id"],),
        ).fetchone()
        extracted = json.loads(row["payload"]) if row else None
    decision_row = conn.execute(
        "SELECT payload FROM gate_decisions WHERE document_id = ? ORDER BY created_at DESC LIMIT 1",
        (document_id,),
    ).fetchone()
    sig = conn.execute(
        "SELECT * FROM signature_requests WHERE document_id = ? ORDER BY created_at DESC LIMIT 1",
        (document_id,),
    ).fetchone()
    audit = []
    for row in conn.execute("SELECT * FROM audit_events WHERE document_id = ? ORDER BY timestamp", (document_id,)):
        item = dict(row)
        item["metadata"] = json.loads(item["metadata"]) if item["metadata"] else None
        audit.append(item)
    pipeline = [dict(r) for r in conn.execute(
        "SELECT * FROM pipeline_steps WHERE document_id = ? ORDER BY seq",
        (document_id,),
    )]
    return {
        "document": document,
        "manifest": _latest_manifest(document_id),
        "approved_manifest": _approved_manifest(document_id),
        "current_version": version,
        "versions": versions,
        "extracted": extracted,
        "decision": json.loads(decision_row["payload"]) if decision_row else None,
        "signature_request": dict(sig) if sig else None,
        "audit": audit,
        "pipeline": pipeline,
        "foxit_configured": foxit_configured(),
    }


def list_documents() -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in _conn().execute(
            "SELECT id, title, status, created_at, updated_at FROM documents ORDER BY updated_at DESC"
        )
    ]


def create_document(prompt: str, actor: str = "human:operator") -> dict[str, Any]:
    manifest = extract_intent(prompt)
    document_id = _id(10)
    ts = _now()
    conn = _conn()
    conn.execute(
        "INSERT INTO documents (id, title, document_type, status, prompt, actor, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (document_id, manifest["title"], manifest["document_type"], "awaiting_approval", prompt, actor, ts, ts),
    )
    conn.execute(
        "INSERT INTO intent_manifests (id, document_id, version, payload, status, created_at) VALUES (?,?,?,?,?,?)",
        (_id(12), document_id, 1, json.dumps(manifest), "draft", ts),
    )
    conn.commit()
    write_audit(
        document_id,
        actor,
        "capture_intent",
        manifest_version=1,
        new_state="awaiting_approval",
        reason="Plain-language request converted to an Intent Manifest. Not yet authorized.",
        metadata={"prompt": prompt},
    )
    record_pipeline(
        document_id,
        "intent_manifest",
        "local",
        "ok",
        "Structured terms extracted from chat. Chat is not authorization.",
    )
    return get_session(document_id)


def update_draft_manifest(document_id: str, payload: dict[str, Any], actor: str = "human:operator") -> dict[str, Any]:
    current = _latest_manifest(document_id)
    if not current:
        raise ValueError("No manifest")
    conn = _conn()
    version = current["version"]
    if current["status"] == "approved":
        conn.execute("UPDATE intent_manifests SET status = 'superseded' WHERE id = ?", (current["id"],))
        version = current["version"] + 1
        conn.execute(
            "INSERT INTO intent_manifests (id, document_id, version, payload, status, created_at) VALUES (?,?,?,?,?,?)",
            (_id(12), document_id, version, json.dumps(payload), "draft", _now()),
        )
    else:
        conn.execute("UPDATE intent_manifests SET payload = ? WHERE id = ?", (json.dumps(payload), current["id"]))
    previous = _document(document_id)["status"]
    conn.execute(
        "UPDATE documents SET title = ?, status = ?, updated_at = ? WHERE id = ?",
        (payload["title"], "awaiting_approval", _now(), document_id),
    )
    conn.commit()
    write_audit(
        document_id,
        actor,
        "edit_manifest",
        manifest_version=version,
        previous_state=previous,
        new_state="awaiting_approval",
        reason="Human edited the structured terms before approval.",
    )
    return get_session(document_id)


def approve_manifest(document_id: str, actor: str = "human:operator", notes: str | None = None) -> dict[str, Any]:
    manifest = _latest_manifest(document_id)
    if not manifest:
        raise ValueError("No manifest to approve")
    conn = _conn()
    conn.execute("UPDATE intent_manifests SET status = 'approved' WHERE id = ?", (manifest["id"],))
    conn.execute(
        "INSERT INTO manifest_approvals (id, manifest_id, actor, approved_at, notes) VALUES (?,?,?,?,?)",
        (_id(12), manifest["id"], actor, _now(), notes),
    )
    previous = _document(document_id)["status"]
    conn.execute("UPDATE documents SET status = ?, updated_at = ? WHERE id = ?", ("approved", _now(), document_id))
    conn.commit()
    write_audit(
        document_id,
        actor,
        "approve_manifest",
        document_hash=fingerprint(checksum_from_manifest(manifest["payload"])),
        manifest_version=manifest["version"],
        previous_state=previous,
        new_state="approved",
        reason="Human authorized the Intent Manifest. This is now the source of truth.",
        metadata={"notes": notes},
    )
    record_pipeline(
        document_id,
        "intent_lock",
        "local",
        "ok",
        f"Manifest v{manifest['version']} locked. Hash {fingerprint(checksum_from_manifest(manifest['payload']))[:16]}…",
    )
    return get_session(document_id)


def _persist_version(document_id: str, source: str, data: bytes, page_count: int, actor: str, notes: str | None = None) -> dict[str, Any]:
    previous = _current_version(document_id)
    version = (previous["version"] if previous else 0) + 1
    sha256 = hashlib.sha256(data).hexdigest()
    directory = files_dir() / document_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"v{version}.pdf"
    path.write_bytes(data)
    conn = _conn()
    conn.execute("UPDATE document_versions SET is_current = 0 WHERE document_id = ?", (document_id,))
    version_id = _id(12)
    conn.execute(
        """INSERT INTO document_versions
           (id, document_id, version, source, file_path, sha256, page_count, created_at, is_current, notes)
           VALUES (?,?,?,?,?,?,?,?,1,?)""",
        (version_id, document_id, version, source, str(path), sha256, page_count, _now(), notes),
    )
    conn.commit()
    write_audit(
        document_id,
        actor,
        f"add_version:{source}",
        document_hash=sha256,
        manifest_version=(_latest_manifest(document_id) or {}).get("version"),
        previous_state=_document(document_id)["status"],
        new_state=_document(document_id)["status"],
        reason=notes or f"Stored document version {version} from {source}.",
        metadata={"version_id": version_id, "page_count": page_count},
    )
    return {"id": version_id, "sha256": sha256, "version": version, "file_path": str(path)}


def _looks_like_scan(data: bytes) -> bool:
    try:
        text = extract_pdf_terms(data)["raw_text"].strip()
        return len(text) < 80
    except Exception:
        return True


def _extract_from_buffer(
    document_id: str,
    data: bytes,
    *,
    scan: bool = False,
    source_text: str | None = None,
) -> tuple[dict[str, Any], str]:
    working = data
    needs_ocr = scan or _looks_like_scan(data)
    if needs_ocr:
        if foxit_configured():
            try:
                working = foxit_ocr(data)
                record_pipeline(
                    document_id,
                    "ocr",
                    "foxit",
                    "ok",
                    "Foxit OCR converted the scan into a searchable PDF.",
                    "pdf-ocr",
                )
            except Exception as exc:
                record_pipeline(
                    document_id,
                    "ocr",
                    "local",
                    "fallback",
                    f"Foxit OCR unavailable ({exc}). Local OCR fallback used.",
                    "pdf-ocr",
                )
                if source_text:
                    extracted = extract_terms_from_pages([source_text])
                    record_pipeline(
                        document_id,
                        "extract",
                        "local",
                        "fallback",
                        "Parser ran on local OCR fallback text. Not recorded as a Foxit success.",
                        "pdf-to-text",
                    )
                    return extracted, "local"
        else:
            record_pipeline(
                document_id,
                "ocr",
                "local",
                "fallback",
                "No Foxit credentials. Local OCR fallback used on the scan's source text.",
                "pdf-ocr",
            )
            if source_text:
                extracted = extract_terms_from_pages([source_text])
                record_pipeline(
                    document_id,
                    "extract",
                    "local",
                    "fallback",
                    "Parser ran on local OCR fallback text.",
                    "pdf-to-text",
                )
                return extracted, "local"

    if foxit_configured():
        try:
            text = foxit_pdf_to_text(working)
            pages = [part for part in text.split("\f") if part]
            record_pipeline(
                document_id,
                "extract",
                "foxit",
                "ok",
                "Foxit Extraction pulled text from the (OCR'd) PDF.",
                "pdf-to-text",
            )
            return extract_terms_from_pages(pages or [text]), "foxit"
        except Exception as exc:
            record_pipeline(
                document_id,
                "extract",
                "local",
                "fallback",
                f"Foxit Extraction unavailable ({exc}). Local parser used.",
                "pdf-to-text",
            )
            if source_text and needs_ocr:
                return extract_terms_from_pages([source_text]), "local"
            return extract_pdf_terms(working), "local"

    record_pipeline(
        document_id,
        "extract",
        "local",
        "ok" if not needs_ocr else "fallback",
        "Local parser extracted terms from the PDF text layer.",
        "pdf-to-text",
    )
    if source_text and needs_ocr:
        return extract_terms_from_pages([source_text]), "local"
    return extract_pdf_terms(working), "local"


def _render_agreement(document_id: str, manifest: dict[str, Any]) -> tuple[bytes, int, str]:
    if foxit_configured():
        try:
            data = foxit_generate_document(agreement_template(), agreement_values(manifest), "pdf")
            pages = pdf_page_count(data)
            record_pipeline(
                document_id,
                "generate",
                "foxit",
                "ok",
                "Foxit Document Generation rendered the agreement from a DOCX template + Intent Manifest values.",
                "GenerateDocumentBase64",
            )
            return data, pages, "foxit_docgen"
        except Exception as exc:
            record_pipeline(
                document_id,
                "generate",
                "foxit",
                "fallback",
                f"DocGen failed ({exc}). Trying Foxit HTML→PDF.",
                "GenerateDocumentBase64",
            )
            try:
                data = foxit_html_to_pdf(agreement_html(manifest))
                pages = pdf_page_count(data)
                record_pipeline(
                    document_id,
                    "generate",
                    "foxit",
                    "ok",
                    "Foxit HTML→PDF rendered the agreement.",
                    "pdf-from-html",
                )
                return data, pages, "foxit_html_to_pdf"
            except Exception as nested:
                record_pipeline(
                    document_id,
                    "generate",
                    "local",
                    "fallback",
                    f"Foxit HTML→PDF failed ({nested}). Local reportlab used. Not a Foxit success.",
                    "pdf-from-html",
                )
    else:
        record_pipeline(
            document_id,
            "generate",
            "local",
            "fallback",
            "No Foxit credentials. Local reportlab generated the agreement PDF.",
            "GenerateDocumentBase64",
        )
    data, pages = generate_agreement_pdf(manifest)
    return data, pages, "local_reportlab"


def _render_cover_sheet(document_id: str, manifest: dict[str, Any]) -> tuple[bytes, str]:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if foxit_configured():
        try:
            data = foxit_generate_document(cover_sheet_template(), cover_sheet_values(manifest, stamp), "pdf")
            record_pipeline(
                document_id,
                "cover_sheet",
                "foxit",
                "ok",
                "Foxit Document Generation created the SignGate Verification Certificate.",
                "GenerateDocumentBase64",
            )
            return data, "foxit_docgen"
        except Exception as exc:
            try:
                data = foxit_html_to_pdf(cover_sheet_html(manifest, stamp))
                record_pipeline(
                    document_id,
                    "cover_sheet",
                    "foxit",
                    "ok",
                    f"DocGen cover sheet failed ({exc}); Foxit HTML→PDF created the certificate.",
                    "pdf-from-html",
                )
                return data, "foxit_html_to_pdf"
            except Exception as nested:
                record_pipeline(
                    document_id,
                    "cover_sheet",
                    "local",
                    "fallback",
                    f"Foxit cover sheet failed ({nested}). Local certificate used.",
                    "GenerateDocumentBase64",
                )
    else:
        record_pipeline(
            document_id,
            "cover_sheet",
            "local",
            "fallback",
            "Local reportlab created the Verification Certificate.",
            "GenerateDocumentBase64",
        )
    return generate_cover_sheet(manifest, stamp), "local_reportlab"


def _merge_cover(document_id: str, cover: bytes, contract: bytes) -> tuple[bytes, str]:
    if foxit_configured():
        try:
            data = foxit_combine([cover, contract])
            record_pipeline(
                document_id,
                "merge",
                "foxit",
                "ok",
                "Foxit Combine appended the Verification Certificate to the front of the contract.",
                "pdf-combine",
            )
            return data, "foxit_combine"
        except Exception as exc:
            record_pipeline(
                document_id,
                "merge",
                "local",
                "fallback",
                f"Foxit Combine unavailable ({exc}). Local merge used. Not a Foxit success.",
                "pdf-combine",
            )
    else:
        record_pipeline(
            document_id,
            "merge",
            "local",
            "fallback",
            "Local merge placed the Verification Certificate on page 1.",
            "pdf-combine",
        )
    return merge_pdfs(cover, contract), "local_merge"


def _compile_with_cover(document_id: str, contract: bytes, manifest: dict[str, Any], actor: str) -> dict[str, Any]:
    if has_cover_sheet(contract):
        return _persist_version(
            document_id,
            "compiled",
            contract,
            pdf_page_count(contract),
            actor,
            "Compiled instrument already includes the Verification Certificate.",
        )
    cover, _via = _render_cover_sheet(document_id, manifest)
    compiled, merge_via = _merge_cover(document_id, cover, contract)
    return _persist_version(
        document_id,
        "compiled",
        compiled,
        pdf_page_count(compiled),
        actor,
        f"Verification Certificate merged to the front ({merge_via}).",
    )


def generate_document(document_id: str, actor: str = "human:operator") -> dict[str, Any]:
    approved = _approved_manifest(document_id)
    if not approved:
        raise ValueError("Approve the Intent Manifest before generating a document.")
    data, page_count, via = _render_agreement(document_id, approved["payload"])
    _persist_version(document_id, "generated", data, page_count, actor, f"Generated via {via}")
    _set_status(document_id, "generated")
    session = verify_current(document_id, actor, f"Generated document compared to approved manifest ({via}).")
    if session["decision"]["status"] == "open":
        _compile_with_cover(document_id, data, approved["payload"], actor)
        session = verify_current(
            document_id,
            actor,
            "Verification Certificate merged. Re-verified before any eSign handoff.",
        )
    return session


def upload_document(
    document_id: str,
    data: bytes,
    actor: str = "human:operator",
    source: str = "uploaded",
    notes: str | None = None,
    scan: bool = False,
    source_text: str | None = None,
    compile_if_open: bool = False,
) -> dict[str, Any]:
    if not _approved_manifest(document_id):
        raise ValueError("Approve the Intent Manifest before verifying a document.")
    pages = 1
    try:
        pages = pdf_page_count(data) or 1
    except Exception:
        pages = 1
    _persist_version(document_id, source, data, pages, actor, notes)
    session = verify_current(
        document_id,
        actor,
        notes or "Uploaded document compared to approved manifest.",
        scan=scan,
        source_text=source_text,
    )
    if compile_if_open and session["decision"]["status"] == "open":
        approved = _approved_manifest(document_id)
        _compile_with_cover(document_id, data, approved["payload"], actor)
        session = verify_current(document_id, actor, "Verification Certificate merged after restore.")
    return session


def introduce_adversary(document_id: str, actor: str = "human:operator") -> dict[str, Any]:
    approved = _approved_manifest(document_id)
    if not approved:
        raise ValueError("Approve and generate an agreement before introducing an adversarial edit.")
    data, _page_count = generate_agreement_pdf(adversarial_manifest(approved["payload"]), adversarial=True)
    return upload_document(
        document_id,
        data,
        actor,
        "adversarial",
        "Adversarial edit: value ×10, 90-day termination, automatic renewal inserted, Statement of Work removed.",
    )


def introduce_scanned_adversary(document_id: str, actor: str = "human:operator") -> dict[str, Any]:
    approved = _approved_manifest(document_id)
    if not approved:
        raise ValueError("Approve and generate an agreement before introducing a scanned sabotage.")
    tampered = adversarial_manifest(approved["payload"])
    scan, source_text = generate_scan_pdf(tampered, adversarial=True)
    record_pipeline(
        document_id,
        "adversary_scan",
        "local",
        "ok",
        "Vendor returned a scanned image of a modified contract ($500k, auto-renewal on, SOW removed).",
    )
    return upload_document(
        document_id,
        scan,
        actor,
        "adversarial_scan",
        "Scanned sabotage: $50k→$500k, auto-renewal enabled, 90-day termination, Statement of Work removed.",
        scan=True,
        source_text=source_text,
    )


def restore_approved(document_id: str, actor: str = "human:operator") -> dict[str, Any]:
    approved = _approved_manifest(document_id)
    if not approved:
        raise ValueError("No approved Intent Manifest to revert to.")
    data, page_count, via = _render_agreement(document_id, approved["payload"])
    _persist_version(
        document_id,
        "generated",
        data,
        page_count,
        actor,
        f"Reverted to approved manifest and regenerated the clean PDF via {via}.",
    )
    _compile_with_cover(document_id, data, approved["payload"], actor)
    return verify_current(
        document_id,
        actor,
        "Reverted to the approved Intent Manifest. Clean PDF regenerated and Verification Certificate merged.",
    )


def verify_current(
    document_id: str,
    actor: str = "human:operator",
    reason: str | None = None,
    scan: bool = False,
    source_text: str | None = None,
) -> dict[str, Any]:
    approved = _approved_manifest(document_id)
    version = _current_version(document_id)
    if not approved or not version:
        raise ValueError("Nothing to verify.")
    data = Path(version["file_path"]).read_bytes()
    extracted, provider = _extract_from_buffer(
        document_id,
        data,
        scan=scan or version["source"] in {"adversarial_scan", "uploaded_scan"},
        source_text=source_text,
    )
    llm_json, llm_used = extract_llm_json(approved["payload"], extracted)
    two_pass = run_two_pass(approved["payload"], extracted, llm_json=llm_json, llm_used=llm_used)
    record_pipeline(
        document_id,
        "two_pass",
        "local",
        "ok",
        (
            "Pass 1 mapped Foxit text to JSON"
            + (" via LLM" if llm_used else " via the deterministic parser")
            + ". Pass 2 compared that JSON to the Intent Manifest with Python != . The model cannot open the gate."
        ),
    )
    decision = decide_gate(
        approved["payload"],
        extracted,
        extra=None,
        llm_used=llm_used,
        two_pass=two_pass,
        cover_sheet_attached=has_cover_sheet(data),
        extraction_provider=provider,
    )
    conn = _conn()
    conn.execute(
        "INSERT INTO extracted_terms (id, version_id, payload, created_at) VALUES (?,?,?,?)",
        (_id(12), version["id"], json.dumps(extracted), _now()),
    )
    decision_id = _id(12)
    conn.execute(
        "INSERT INTO gate_decisions (id, document_id, version_id, manifest_id, status, payload, created_at) VALUES (?,?,?,?,?,?,?)",
        (decision_id, document_id, version["id"], approved["id"], decision["status"], json.dumps(decision), _now()),
    )
    for item in decision["discrepancies"]:
        conn.execute(
            "INSERT INTO discrepancies (id, gate_decision_id, version_id, severity, layer, field, payload) VALUES (?,?,?,?,?,?,?)",
            (item["id"], decision_id, version["id"], item["severity"], item["layer"], item["field"], json.dumps(item)),
        )
    previous = _document(document_id)["status"]
    next_status = "verified_open" if decision["status"] == "open" else "verified_blocked"
    conn.execute("UPDATE documents SET status = ?, updated_at = ? WHERE id = ?", (next_status, _now(), document_id))
    conn.commit()
    write_audit(
        document_id,
        actor,
        "verify",
        document_hash=version["sha256"],
        manifest_version=approved["version"],
        previous_state=previous,
        new_state=next_status,
        reason=reason or "Final document compared against the approved Intent Manifest.",
        metadata={
            "gate": decision["status"],
            "critical": decision["critical_count"],
            "material": decision["material_count"],
            "llm_used": decision["llm_used"],
            "two_pass": True,
            "cover_sheet_attached": decision.get("cover_sheet_attached"),
        },
    )
    return get_session(document_id)


def request_signature(document_id: str, actor: str = "human:operator", signer_email: str | None = None) -> dict[str, Any]:
    session = get_session(document_id)
    if not session["decision"] or session["decision"]["status"] != "open":
        raise ValueError("SIGNATURE GATE: BLOCKED. The eSign API is not called until verification opens the gate.")
    if not session["approved_manifest"] or not session["current_version"]:
        raise ValueError("Missing approved manifest or document version.")
    data = Path(session["current_version"]["file_path"]).read_bytes()
    if not has_cover_sheet(data):
        _compile_with_cover(document_id, data, session["approved_manifest"]["payload"], actor)
        session = verify_current(document_id, actor, "Cover sheet merged immediately before eSign.")
        if session["decision"]["status"] != "open":
            raise ValueError("SIGNATURE GATE: BLOCKED after cover-sheet compile.")
        data = Path(session["current_version"]["file_path"]).read_bytes()
    gate = _conn().execute(
        "SELECT id FROM gate_decisions WHERE document_id = ? ORDER BY created_at DESC LIMIT 1",
        (document_id,),
    ).fetchone()
    email = signer_email or session["approved_manifest"]["payload"]["signer"]["email"]
    name = session["approved_manifest"]["payload"]["signer"]["name"]
    pages = pdf_page_count(data)
    provider, provider_ref, raw = "simulated", f"sim_{_id(8)}", {
        "simulated": True,
        "message": "Human signing desk prepared. Agent cannot complete the signature.",
        "cover_sheet": True,
        "page_count": pages,
    }
    if foxit_configured():
        try:
            result = foxit_create_envelope(
                session["document"]["title"],
                email,
                name,
                data,
                page_number=pages,
            )
            provider, provider_ref, raw = result["provider"], result["provider_ref"], result["raw"]
            record_pipeline(
                document_id,
                "esign",
                "foxit",
                "ok",
                "Foxit eSign createfolder called only after the gate opened. Cover sheet is page 1.",
                "createfolder",
            )
        except Exception as exc:
            record_pipeline(
                document_id,
                "esign",
                "local",
                "fallback",
                f"Foxit eSign failed ({exc}). Local human signing desk prepared. Not a Foxit success.",
                "createfolder",
            )
            raw = {
                "simulated": True,
                "foxit_error": str(exc),
                "message": "Foxit eSign call failed; prepared a local human signing desk instead.",
                "cover_sheet": True,
            }
    else:
        record_pipeline(
            document_id,
            "esign",
            "local",
            "fallback",
            "No Foxit credentials. Local human signing desk prepared after the gate opened.",
            "createfolder",
        )
    request_id = _id(12)
    _conn().execute(
        """INSERT INTO signature_requests
           (id, document_id, version_id, gate_decision_id, provider, provider_ref, signer_email, status, created_at, raw)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            request_id,
            document_id,
            session["current_version"]["id"],
            gate["id"],
            provider,
            provider_ref,
            email,
            "prepared",
            _now(),
            json.dumps(raw),
        ),
    )
    _conn().commit()
    _set_status(document_id, "sent_for_signature")
    write_audit(
        document_id,
        actor,
        "prepare_signature",
        document_hash=session["current_version"]["sha256"],
        manifest_version=session["approved_manifest"]["version"],
        previous_state="verified_open",
        new_state="sent_for_signature",
        reason="Gate was open. Prepared a signature request for a human signer. The agent did not sign.",
        metadata={"provider": provider, "provider_ref": provider_ref, "signer_email": email, "cover_sheet": True},
    )
    return get_session(document_id)


def complete_human_signature(document_id: str, actor: str = "human:signer") -> dict[str, Any]:
    session = get_session(document_id)
    if not session["signature_request"]:
        raise ValueError("No signature request")
    if session["document"]["status"] != "sent_for_signature":
        raise ValueError("Signature handoff is not active.")
    _conn().execute("UPDATE signature_requests SET status = 'signed' WHERE id = ?", (session["signature_request"]["id"],))
    _conn().commit()
    write_audit(
        document_id,
        actor,
        "human_sign",
        document_hash=(session["current_version"] or {}).get("sha256"),
        manifest_version=(session["approved_manifest"] or {}).get("version"),
        previous_state="sent_for_signature",
        new_state="sent_for_signature",
        reason="A human completed the legally meaningful signing action.",
        metadata={"signature_request_id": session["signature_request"]["id"]},
    )
    return get_session(document_id)


def pdf_bytes(document_id: str) -> bytes:
    version = _current_version(document_id)
    if not version:
        raise ValueError("No PDF yet")
    return Path(version["file_path"]).read_bytes()


def wrap_upload_as_scan(data: bytes, filename: str) -> bytes:
    lower = filename.lower()
    if lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")):
        return image_to_scan_pdf(data)
    return data


def build_receipt(document_id: str) -> tuple[bytes, dict[str, Any]]:
    session = get_session(document_id)
    findings = [
        f"{item['severity'].upper()} · {item['title']}: approved {item['approved_value']} / found {item['found_value']}"
        for item in (session["decision"] or {}).get("discrepancies", [])
    ]
    pdf = generate_receipt_pdf(
        document_id,
        session["document"]["title"],
        (session["decision"] or {}).get("status", "closed"),
        (session["decision"] or {}).get("semantic_checksum", "n/a"),
        session["document"]["actor"],
        findings,
    )
    return pdf, {
        "document": session["document"],
        "approved_manifest": (session["approved_manifest"] or {}).get("payload"),
        "semantic_checksum": (session["decision"] or {}).get("semantic_checksum"),
        "gate": (session["decision"] or {}).get("status", "closed"),
        "discrepancies": (session["decision"] or {}).get("discrepancies", []),
        "two_pass": (session["decision"] or {}).get("two_pass"),
        "pipeline": session.get("pipeline"),
        "audit": session["audit"],
        "generated_at": _now(),
        "argument": (
            "Foxit left signing out of the agent toolset. A bare handoff is still a vulnerability: "
            "humans suffer from review fatigue. SignGate is the cryptographic and semantic firewall."
        ),
    }
