from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .checksum import checksum_from_manifest, fingerprint
from .db import connect, files_dir
from .extract import extract_terms_from_pages
from .foxit import foxit_configured, foxit_create_envelope, foxit_html_to_pdf, foxit_pdf_to_text
from .intent import adversarial_manifest, extract_intent
from .pdf import agreement_html, extract_pdf_terms, generate_agreement_pdf, generate_receipt_pdf
from .semantic import propose_semantic_findings
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


def _extract_from_buffer(data: bytes):
    if foxit_configured():
        try:
            text = foxit_pdf_to_text(data)
            pages = [part for part in text.split("\f") if part]
            return extract_terms_from_pages(pages or [text])
        except Exception:
            return extract_pdf_terms(data)
    return extract_pdf_terms(data)


def generate_document(document_id: str, actor: str = "human:operator") -> dict[str, Any]:
    approved = _approved_manifest(document_id)
    if not approved:
        raise ValueError("Approve the Intent Manifest before generating a document.")
    via = "local_reportlab"
    if foxit_configured():
        try:
            data = foxit_html_to_pdf(agreement_html(approved["payload"]))
            extracted = _extract_from_buffer(data)
            page_count = extracted["page_count"] or 3
            via = "foxit_html_to_pdf"
        except Exception:
            data, page_count = generate_agreement_pdf(approved["payload"])
            via = "local_reportlab_fallback"
    else:
        data, page_count = generate_agreement_pdf(approved["payload"])
    _persist_version(document_id, "generated", data, page_count, actor, f"Generated via {via}")
    _set_status(document_id, "generated")
    return verify_current(document_id, actor, f"Generated document compared to approved manifest ({via}).")


def upload_document(
    document_id: str,
    data: bytes,
    actor: str = "human:operator",
    source: str = "uploaded",
    notes: str | None = None,
) -> dict[str, Any]:
    if not _approved_manifest(document_id):
        raise ValueError("Approve the Intent Manifest before verifying a document.")
    probe = _extract_from_buffer(data)
    _persist_version(document_id, source, data, probe["page_count"] or 1, actor, notes)
    return verify_current(document_id, actor, notes or "Uploaded document compared to approved manifest.")


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


def restore_approved(document_id: str, actor: str = "human:operator") -> dict[str, Any]:
    row = _conn().execute(
        "SELECT * FROM document_versions WHERE document_id = ? AND source = 'generated' ORDER BY version DESC LIMIT 1",
        (document_id,),
    ).fetchone()
    if not row:
        raise ValueError("No approved generated version to restore.")
    return upload_document(
        document_id,
        Path(row["file_path"]).read_bytes(),
        actor,
        "restored",
        "Restored the last generated approved document.",
    )


def verify_current(document_id: str, actor: str = "human:operator", reason: str | None = None) -> dict[str, Any]:
    approved = _approved_manifest(document_id)
    version = _current_version(document_id)
    if not approved or not version:
        raise ValueError("Nothing to verify.")
    extracted = _extract_from_buffer(Path(version["file_path"]).read_bytes())
    extra, llm_used = propose_semantic_findings(approved["payload"], extracted)
    decision = decide_gate(approved["payload"], extracted, extra, llm_used)
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
        },
    )
    return get_session(document_id)


def request_signature(document_id: str, actor: str = "human:operator", signer_email: str | None = None) -> dict[str, Any]:
    session = get_session(document_id)
    if not session["decision"] or session["decision"]["status"] != "open":
        raise ValueError("SIGNATURE GATE: BLOCKED. The eSign API is not called until verification opens the gate.")
    if not session["approved_manifest"] or not session["current_version"]:
        raise ValueError("Missing approved manifest or document version.")
    gate = _conn().execute(
        "SELECT id FROM gate_decisions WHERE document_id = ? ORDER BY created_at DESC LIMIT 1",
        (document_id,),
    ).fetchone()
    email = signer_email or session["approved_manifest"]["payload"]["signer"]["email"]
    name = session["approved_manifest"]["payload"]["signer"]["name"]
    provider, provider_ref, raw = "simulated", f"sim_{_id(8)}", {
        "simulated": True,
        "message": "Human signing desk prepared. Agent cannot complete the signature.",
    }
    if foxit_configured():
        try:
            result = foxit_create_envelope(
                session["document"]["title"],
                email,
                name,
                Path(session["current_version"]["file_path"]).read_bytes(),
            )
            provider, provider_ref, raw = result["provider"], result["provider_ref"], result["raw"]
        except Exception as exc:
            raw = {
                "simulated": True,
                "foxit_error": str(exc),
                "message": "Foxit eSign call failed; prepared a local human signing desk instead.",
            }
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
        metadata={"provider": provider, "provider_ref": provider_ref, "signer_email": email},
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
        "audit": session["audit"],
        "generated_at": _now(),
    }
