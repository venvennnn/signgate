from __future__ import annotations

import copy
import json

import streamlit as st

from signgate.foxit import foxit_configured
from signgate.intent import DEFAULT_PROMPT
from signgate.workflow import (
    approve_manifest,
    build_receipt,
    complete_human_signature,
    create_document,
    generate_document,
    get_session,
    introduce_adversary,
    introduce_scanned_adversary,
    list_documents,
    pdf_bytes,
    request_signature,
    restore_approved,
    update_draft_manifest,
    upload_document,
    wrap_upload_as_scan,
)

st.set_page_config(
    page_title="SignGate — cryptographic and semantic firewall",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"],
      [data-testid="stSidebar"], [data-testid="stBottom"], .stApp, .main, .block-container {
        background: #ffffff !important;
        color: #1b1a16;
      }
      [data-testid="stSidebar"] { background: #ffffff !important; border-right: 1px solid #ece6da; }
      [data-testid="stToolbar"] { display: none; }
      h1, h2, h3 { font-family: "Times New Roman", Times, serif !important; color: #1b1a16 !important; }
      .block-container { padding-top: 1.4rem; max-width: 1200px; }
      .sg-kicker {
        font-size: 12px; letter-spacing: 0.18em; text-transform: uppercase;
        color: #8a6a2f; font-weight: 600;
      }
      .sg-card, .sg-arg, .sg-finding, .sg-step {
        border: 1px solid #ece6da; background: #fff; padding: 1.1rem 1.2rem; margin-bottom: 1rem;
      }
      .sg-arg { border-left: 4px solid #8a6a2f; background: #fbf8f2; }
      .sg-seal {
        width: 160px; height: 160px; margin: 0 auto 1rem;
        border-radius: 999px; display: grid; place-items: center; text-align: center;
        letter-spacing: 0.12em; font-weight: 700; border: 7px double currentColor;
      }
      .sg-blocked-flash {
        animation: sgflash 0.9s ease 0s 4;
        border: 2px solid #b42318;
        background: #fff5f4;
        padding: 1rem 1.1rem;
        margin-bottom: 1rem;
      }
      @keyframes sgflash {
        0%, 100% { box-shadow: 0 0 0 0 rgba(180,35,24,0); }
        50% { box-shadow: 0 0 0 10px rgba(180,35,24,0.12); }
      }
      .sg-lock {
        display: inline-block; border: 1px solid #0b7a4b; color: #0b7a4b;
        letter-spacing: .16em; font-size: 11px; padding: 4px 10px; font-weight: 700;
      }
      .sg-finding { border: 1px solid #ece6da; padding: 0.75rem 0.9rem; margin-bottom: 0.6rem; }
      .sg-finding.critical, .sg-finding.material { border-color: #b42318; background: #fff8f7; }
      .stButton>button {
        border-radius: 0; border: 1px solid #1b1a16; background: #1b1a16; color: #fff;
      }
      .stButton>button:hover { background: #000; color: #fff; border-color: #000; }
      .stButton>button[kind="secondary"] { background: #fff; color: #1b1a16; }
      textarea, input, [data-baseweb="input"] { background: #fff !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

ARGUMENT = (
    "Foxit deliberately left signing out of the agent's toolset. We believe that was the correct choice, "
    "but it didn't go far enough. A simple handoff is a security vulnerability, because humans suffer from "
    "review fatigue. If an agent drafts a 40-page document, the human signer will assume it's correct. "
    "The boundary between agent and signer shouldn't just be a handoff — it must be a cryptographic and "
    "semantic firewall. SignGate is that firewall."
)

if "document_id" not in st.session_state:
    st.session_state.document_id = None
if "error" not in st.session_state:
    st.session_state.error = None


def _err(exc: Exception) -> None:
    st.session_state.error = str(exc)


def _clear_err() -> None:
    st.session_state.error = None


def _argument() -> None:
    st.markdown(
        f'<div class="sg-arg"><p class="sg-kicker">The argument</p><p>{ARGUMENT}</p></div>',
        unsafe_allow_html=True,
    )


def render_home() -> None:
    st.markdown('<p class="sg-kicker">Authorization integrity</p>', unsafe_allow_html=True)
    st.title("The agent drafts. The human authorizes. SignGate is the firewall.")
    _argument()
    st.write(
        "Chat is not authorization. The approved Intent Manifest is the source of truth. "
        "Foxit OCR, Extraction, Document Generation, Combine, and eSign run as tools inside that boundary — "
        "eSign is unreachable until the gate opens."
    )

    if "prompt_box" not in st.session_state:
        st.session_state.prompt_box = DEFAULT_PROMPT
    c1, c2, _c3 = st.columns([1, 1, 2])
    load_demo = c1.button("Load 3-minute demo", type="secondary")
    lock_manifest = c2.button("Lock Intent Manifest", key="extract_intent")
    if load_demo:
        st.session_state.prompt_box = DEFAULT_PROMPT
    prompt = st.text_area("Capture intent", height=120, key="prompt_box")
    if lock_manifest:
        try:
            session = create_document(prompt or DEFAULT_PROMPT)
            st.session_state.document_id = session["document"]["id"]
            _clear_err()
            st.rerun()
        except Exception as exc:
            _err(exc)

    st.caption("0:00–0:30 · The structured JSON locks. Chat never becomes a signature.")

    cols = st.columns(3)
    for col, (num, title, body) in zip(
        cols,
        [
            ("01", "Intent Manifest", "Parties, money, notice, renewal, law, and prohibited clauses become the source of truth."),
            ("02", "Two-pass checksum", "An LLM may map Foxit text to JSON. Python compares field-for-field. The model cannot open the gate."),
            ("03", "Cover sheet → eSign", "Foxit generates a Verification Certificate, Combine puts it on page 1, then eSign is called."),
        ],
    ):
        with col:
            st.markdown(f'<div class="sg-card"><p class="sg-kicker">{num}</p><h3>{title}</h3><p>{body}</p></div>', unsafe_allow_html=True)

    recent = list_documents()
    if recent:
        st.subheader("Recent instruments")
        for row in recent:
            if st.button(f"{row['title']}  ·  {row['status'].replace('_', ' ')}", key=f"open-{row['id']}", type="secondary"):
                st.session_state.document_id = row["id"]
                _clear_err()
                st.rerun()


def _manifest_editor(payload: dict, locked: bool) -> dict:
    draft = copy.deepcopy(payload)
    a, b = st.columns(2)
    draft["parties"]["customer"] = a.text_input("Customer", draft["parties"]["customer"], disabled=locked)
    draft["parties"]["vendor"] = b.text_input("Vendor", draft["parties"]["vendor"], disabled=locked)
    c, d = st.columns(2)
    draft["commercial_terms"]["contract_value"]["currency"] = c.text_input(
        "Currency", draft["commercial_terms"]["contract_value"]["currency"], disabled=locked
    )
    draft["commercial_terms"]["contract_value"]["amount"] = d.number_input(
        "Contract value", value=int(draft["commercial_terms"]["contract_value"]["amount"]), step=1000, disabled=locked
    )
    e, f, g = st.columns(3)
    draft["commercial_terms"]["term_months"] = e.number_input(
        "Term (months)", value=int(draft["commercial_terms"]["term_months"]), disabled=locked
    )
    draft["commercial_terms"]["payment_terms_days"] = f.number_input(
        "Payment terms (days)", value=int(draft["commercial_terms"]["payment_terms_days"]), disabled=locked
    )
    draft["legal_terms"]["termination_notice_days"] = g.number_input(
        "Termination notice (days)", value=int(draft["legal_terms"]["termination_notice_days"]), disabled=locked
    )
    h, i = st.columns(2)
    draft["legal_terms"]["governing_law"] = h.text_input(
        "Governing law", draft["legal_terms"]["governing_law"], disabled=locked
    )
    draft["signer"]["email"] = i.text_input("Signer email", draft["signer"]["email"], disabled=locked)
    x, y, z = st.columns(3)
    draft["legal_terms"]["auto_renewal"] = x.checkbox("Automatic renewal", value=draft["legal_terms"]["auto_renewal"], disabled=locked)
    draft["legal_terms"]["personal_guarantee"] = y.checkbox(
        "Personal guarantee", value=draft["legal_terms"]["personal_guarantee"], disabled=locked
    )
    draft["legal_terms"]["exclusivity"] = z.checkbox("Exclusivity", value=draft["legal_terms"]["exclusivity"], disabled=locked)
    draft["required_attachments"] = [
        part.strip()
        for part in st.text_input(
            "Required attachments",
            ", ".join(draft["required_attachments"]),
            disabled=locked,
        ).split(",")
        if part.strip()
    ]
    draft["must_not_include"] = [
        part.strip()
        for part in st.text_input(
            "Must not include",
            ", ".join(draft["must_not_include"]),
            disabled=locked,
        ).split(",")
        if part.strip()
    ]
    return draft


def _pipeline(session: dict) -> None:
    st.markdown("### Foxit toolpath")
    st.caption("OCR → Extract → Generate → Merge → eSign. Local fallbacks are labeled. We never fake a Foxit success.")
    known = [
        ("ocr", "OCR", "pdf-ocr"),
        ("extract", "Extract", "pdf-to-text"),
        ("generate", "Generate", "GenerateDocumentBase64"),
        ("cover_sheet", "Certificate", "GenerateDocumentBase64"),
        ("merge", "Merge", "pdf-combine"),
        ("esign", "eSign", "createfolder"),
    ]
    by_tool = {}
    for step in session.get("pipeline") or []:
        by_tool[step["tool"]] = step
    cols = st.columns(len(known))
    for col, (tool, label, op) in zip(cols, known):
        step = by_tool.get(tool)
        if not step:
            color, text = "#6d675c", "pending"
        elif step["provider"] == "foxit" and step["status"] == "ok":
            color, text = "#0b7a4b", "Foxit"
        elif step["status"] == "fallback":
            color, text = "#9a6700", "local"
        else:
            color, text = "#1b1a16", step["status"]
        with col:
            st.markdown(
                f'<div class="sg-step" style="min-height:7.2rem"><p class="sg-kicker">{label}</p>'
                f'<div style="color:{color};font-weight:700">{text}</div>'
                f'<div style="font-size:12px;color:#6d675c">{op}</div></div>',
                unsafe_allow_html=True,
            )
    if session.get("pipeline"):
        with st.expander("Pipeline log"):
            for step in session["pipeline"]:
                st.caption(
                    f"{step['seq']:02d} · {step['tool']} · {step['provider']}/{step['status']} — {step['detail']}"
                )


def _two_pass(decision: dict | None) -> None:
    st.markdown("### Two-pass semantic checksum")
    st.caption(
        "Pass 1 maps Foxit-extracted text onto the Intent Manifest schema. "
        "Pass 2 is Python: if extracted_json[field] != manifest_json[field], the gate blocks. "
        "The LLM never declares the contract safe."
    )
    if not decision:
        st.write("Generate or upload a document to run both passes.")
        return
    two = decision.get("two_pass") or {}
    a, b, c = st.columns(3)
    a.json({"approved": two.get("approved_json")})
    b.json({"pass_1_parser": two.get("parser_json")})
    c.json({"pass_1_llm": two.get("llm_json") or {"status": "LLM not configured — parser JSON used"}})
    mismatches = (two.get("parser_mismatches") or []) + (two.get("llm_mismatches") or [])
    if two.get("llm_parser_conflicts"):
        st.warning(
            "LLM JSON disagreed with parser JSON. Deterministic parser wins. "
            + ", ".join(item["field"] for item in two["llm_parser_conflicts"])
        )
    if mismatches:
        st.error(
            "Pass 2 blocked: "
            + ", ".join(f"{m['field']} ({m['source']})" for m in mismatches)
        )
    else:
        st.success("Pass 2: every canonical field equals the locked Intent Manifest.")


def render_workspace(session: dict) -> None:
    document = session["document"]
    decision = session["decision"]
    extracted = session["extracted"]
    gate = (decision or {}).get("status")

    top_l, top_r = st.columns([4, 1])
    with top_l:
        if st.button("← New request", type="secondary", key="new_request"):
            st.session_state.document_id = None
            st.rerun()
        st.markdown('<p class="sg-kicker">SignGate · cryptographic and semantic firewall</p>', unsafe_allow_html=True)
        st.title(document["title"])
        st.write(document["prompt"])
        st.caption(
            f"{document['id']}  ·  {document['status'].replace('_', ' ')}  ·  "
            f"{'Foxit connected' if foxit_configured() else 'Local PDF engine — Foxit tools fall back without faking success'}"
        )
    with top_r:
        if gate == "open":
            color, label = "#0b7a4b", "OPEN"
        elif gate == "blocked":
            color, label = "#b42318", "BLOCKED"
        else:
            color, label = "#6d675c", "CLOSED"
        st.markdown(
            f'<div class="sg-seal" style="color:{color}"><div><div class="sg-kicker">Signature gate</div>'
            f'<div style="font-size:28px;font-family:Times New Roman,serif;margin-top:6px">{label}</div></div></div>',
            unsafe_allow_html=True,
        )
        if decision:
            st.caption(f"Checksum {decision['semantic_checksum'][:16]}")
            if decision["semantic_checksum"] == decision["extracted_checksum"]:
                st.success("Meaning fingerprint matches.")
            else:
                st.error("Meaning fingerprint mismatch.")

    if st.session_state.error:
        st.error(st.session_state.error)

    if gate == "blocked":
        altered = [
            item
            for item in (decision or {}).get("discrepancies", [])
            if item.get("severity") in {"critical", "material"}
        ]
        names = ", ".join(item["title"] for item in altered[:4]) or "material terms"
        st.markdown(
            f'<div class="sg-blocked-flash"><p class="sg-kicker">Signature gate</p>'
            f"<h3>BLOCKED — eSign was not called</h3><p>Altered clauses: {names}</p></div>",
            unsafe_allow_html=True,
        )

    _pipeline(session)

    manifest = session["manifest"]
    approved = session["approved_manifest"]
    locked = bool(approved) and document["status"] != "awaiting_approval"

    st.markdown("### Intent Manifest")
    if approved:
        st.markdown('<span class="sg-lock">LOCKED</span>', unsafe_allow_html=True)
        st.caption(f"Approved v{approved['version']} · this JSON is the only authorization.")
        st.json(approved["payload"])
    else:
        st.caption("Awaiting human approval — JSON is visible, not yet a legal act.")
    draft = _manifest_editor(manifest["payload"], locked) if manifest else None

    b1, b2, b3, b4 = st.columns(4)
    if draft and not locked and b1.button("Save draft", type="secondary", key="save_draft"):
        try:
            update_draft_manifest(document["id"], draft)
            _clear_err()
            st.rerun()
        except Exception as exc:
            _err(exc)
    if b2.button(
        "Approve these terms",
        disabled=bool(approved) and document["status"] != "awaiting_approval",
        key="approve_terms",
    ):
        try:
            if draft and not locked:
                update_draft_manifest(document["id"], draft)
            approve_manifest(document["id"])
            _clear_err()
            st.rerun()
        except Exception as exc:
            _err(exc)
    if b3.button("Generate agreement PDF", disabled=not approved, key="generate_pdf"):
        try:
            generate_document(document["id"])
            _clear_err()
            st.rerun()
        except Exception as exc:
            _err(exc)
    if b4.button(
        "Sabotage as scanned image",
        disabled=not session["current_version"],
        type="secondary",
        key="adversary_scan",
    ):
        try:
            introduce_scanned_adversary(document["id"])
            _clear_err()
            st.rerun()
        except Exception as exc:
            _err(exc)

    r1, r2 = st.columns(2)
    if r1.button(
        "Revert to Approved Manifest",
        disabled=not approved,
        key="restore_pdf",
    ):
        try:
            restore_approved(document["id"])
            _clear_err()
            st.rerun()
        except Exception as exc:
            _err(exc)
    if r2.button(
        "Sabotage as text PDF",
        disabled=not session["current_version"],
        type="secondary",
        key="adversary",
    ):
        try:
            introduce_adversary(document["id"])
            _clear_err()
            st.rerun()
        except Exception as exc:
            _err(exc)

    st.markdown("### Verification")
    st.caption("Exact values, structure, and legal meaning. Pass 2 is Python. The LLM cannot open the gate.")
    if decision:
        st.write(
            f"{decision['verified_term_count']} terms checked · "
            f"{len(decision['missing_attachments'])} missing attachments · "
            f"{len(decision['discrepancies'])} findings"
        )
        if not decision["discrepancies"]:
            st.success("0 material discrepancies. Semantic checksum holds. Cover sheet is eligible.")
        for item in decision["discrepancies"]:
            color = {
                "critical": "#b42318",
                "material": "#b42318",
                "uncertain": "#8a6a2f",
                "clarifying": "#2450c0",
            }.get(item["severity"], "#6d675c")
            page = f" · p.{item['page']}" if item.get("page") else ""
            excerpt = f"<p style='color:#6d675c;font-size:12px'>“{item['excerpt']}”</p>" if item.get("excerpt") else ""
            klass = "critical" if item["severity"] in {"critical", "material"} else ""
            st.markdown(
                f"""<div class="sg-finding {klass}">
                <div style="color:{color};font-size:11px;letter-spacing:.14em;text-transform:uppercase">{item['severity']} · {item['layer']}{page}</div>
                <strong>{item['title']}</strong>
                <div>Approved {item['approved_value']} → Final {item['found_value']}</div>
                <div style="color:#6d675c;font-size:13px">{item['rationale']}</div>
                {excerpt}
                </div>""",
                unsafe_allow_html=True,
            )
    else:
        st.write("Generate or upload a document to run verification.")

    _two_pass(decision)

    if extracted:
        st.markdown("#### Extracted terms")
        value = extracted["commercial_terms"]["contract_value"]
        st.write(
            {
                "Value": f"{value['currency']} {value['amount']:,}" if value else "—",
                "Notice": f"{extracted['legal_terms']['termination_notice_days']} days"
                if extracted["legal_terms"]["termination_notice_days"] is not None
                else "—",
                "Auto-renew": {True: "Yes", False: "No"}.get(extracted["legal_terms"]["auto_renewal"], "—"),
                "Law": extracted["legal_terms"]["governing_law"] or "—",
                "Guarantee": {True: "Yes", False: "No"}.get(extracted["legal_terms"]["personal_guarantee"], "—"),
            }
        )

    if session["current_version"]:
        st.caption(
            f"Final document v{session['current_version']['version']} · {session['current_version']['source']}"
        )
        st.download_button(
            "Download current PDF (cover sheet is page 1 when the gate is open)",
            data=pdf_bytes(document["id"]),
            file_name=f"signgate-{document['id']}.pdf",
            mime="application/pdf",
            key="download_pdf",
        )

    uploaded = st.file_uploader(
        "Or upload a vendor scan (PDF, PNG, JPG) to verify against the approved manifest",
        type=["pdf", "png", "jpg", "jpeg"],
        key="upload_pdf",
    )
    if uploaded is not None and st.button("Verify uploaded scan", key="verify_upload"):
        try:
            payload = wrap_upload_as_scan(uploaded.getvalue(), uploaded.name)
            is_scan = not uploaded.name.lower().endswith(".pdf") or "scan" in uploaded.name.lower()
            upload_document(
                document["id"],
                payload,
                source="uploaded_scan" if is_scan else "uploaded",
                scan=is_scan,
            )
            _clear_err()
            st.rerun()
        except Exception as exc:
            _err(exc)

    st.markdown("### Human signing handoff")
    if gate == "open":
        st.write(
            "Verification passed. SignGate will merge the Verification Certificate (if needed) and call Foxit eSign. "
            "The agent still cannot sign."
        )
    else:
        st.write("The eSign API is unreachable until the gate opens. That is the product.")
    s1, s2 = st.columns(2)
    if s1.button("Prepare signature request", disabled=gate != "open", key="prepare_esign"):
        try:
            request_signature(document["id"])
            _clear_err()
            st.rerun()
        except Exception as exc:
            _err(exc)
    if session["signature_request"]:
        st.info(
            f"Signing desk ready for {session['approved_manifest']['payload']['signer']['name']}. "
            f"Provider: {session['signature_request']['provider']} · {session['signature_request']['status']}. "
            "Page 1 is the SignGate Verification Certificate."
        )
        if session["signature_request"]["status"] != "signed":
            if s2.button("I have reviewed the verified document and I sign", key="human_sign"):
                try:
                    name = session["approved_manifest"]["payload"]["signer"]["name"]
                    complete_human_signature(document["id"], actor=f"human:{name}")
                    _clear_err()
                    st.rerun()
                except Exception as exc:
                    _err(exc)
        else:
            st.success("Signed. The audit trail now records a human actor.")

    receipt_pdf, receipt_json = build_receipt(document["id"])
    d1, d2 = st.columns(2)
    d1.download_button("Download audit JSON", data=json.dumps(receipt_json, indent=2), file_name=f"signgate-{document['id']}.json")
    d2.download_button("Download audit receipt PDF", data=receipt_pdf, file_name=f"signgate-receipt-{document['id']}.pdf")

    st.markdown("### Audit trail")
    for event in session["audit"]:
        st.caption(
            f"{event['timestamp'][:19].replace('T', ' ')}  ·  {event['action']}  ·  {event['actor']}"
            + (f" — {event['reason']}" if event.get("reason") else "")
        )


def main() -> None:
    with st.sidebar:
        st.markdown("**SignGate**")
        st.caption("Agents draft. Humans authorize. SignGate is the firewall.")
        st.markdown(
            """
            **3-minute demo**
            1. 0:00 Capture $50k / 12 months / 30-day / no auto-renewal. JSON locks.
            2. 0:30 Approve → generate (Foxit DocGen).
            3. 0:45 Sabotage as scanned image ($500k, auto-renewal).
            4. 1:15 Foxit OCR + extract. Gate **BLOCKED**. Two clauses highlighted.
            5. 2:00 Revert to Approved Manifest. Foxit regenerates, merges the certificate.
            6. 2:30 Gate **OPEN**. Foxit eSign. Cover sheet is page 1.
            """
        )
        st.caption(ARGUMENT)
        if st.session_state.error:
            st.error(st.session_state.error)

    if st.session_state.document_id:
        try:
            render_workspace(get_session(st.session_state.document_id))
        except Exception as exc:
            st.error(str(exc))
    else:
        render_home()


main()
