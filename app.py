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
    list_documents,
    pdf_bytes,
    request_signature,
    restore_approved,
    update_draft_manifest,
    upload_document,
)

st.set_page_config(
    page_title="SignGate — Agents draft. Humans authorize.",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"],
      [data-testid="stSidebar"], .stApp {
        background: #ffffff !important;
        color: #1b1a16;
      }
      [data-testid="stHeader"] { background: #ffffff !important; }
      [data-testid="stSidebar"] { background: #faf8f4 !important; border-right: 1px solid #ece6da; }
      [data-testid="stToolbar"] { display: none; }
      h1, h2, h3 { font-family: "Times New Roman", Times, serif !important; color: #1b1a16 !important; }
      .block-container { padding-top: 1.4rem; max-width: 1200px; }
      .sg-kicker {
        font-size: 12px; letter-spacing: 0.18em; text-transform: uppercase;
        color: #8a6a2f; font-weight: 600;
      }
      .sg-card {
        border: 1px solid #ece6da; background: #fff; padding: 1.1rem 1.2rem; margin-bottom: 1rem;
      }
      .sg-seal {
        width: 160px; height: 160px; margin: 0 auto 1rem;
        border-radius: 999px; display: grid; place-items: center; text-align: center;
        letter-spacing: 0.12em; font-weight: 700; border: 7px double currentColor;
      }
      .sg-finding { border: 1px solid #ece6da; padding: 0.75rem 0.9rem; margin-bottom: 0.6rem; }
      .stButton>button {
        border-radius: 0; border: 1px solid #1b1a16; background: #1b1a16; color: #fff;
      }
      .stButton>button:hover { background: #000; color: #fff; border-color: #000; }
      .stButton>button[kind="secondary"] {
        background: #fff; color: #1b1a16;
      }
      textarea, input, [data-baseweb="input"] { background: #fff !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

if "document_id" not in st.session_state:
    st.session_state.document_id = None
if "error" not in st.session_state:
    st.session_state.error = None


def _err(exc: Exception) -> None:
    st.session_state.error = str(exc)


def _clear_err() -> None:
    st.session_state.error = None


def render_home() -> None:
    st.markdown('<p class="sg-kicker">Authorization integrity</p>', unsafe_allow_html=True)
    st.title("Prove the final PDF is still the deal a human approved.")
    st.write(
        "The most dangerous document is almost identical to the approved version, except for one material change. "
        "SignGate extracts an Intent Manifest, requires human approval, then blocks eSign if the PDF diverges."
    )

    if "prompt_box" not in st.session_state:
        st.session_state.prompt_box = DEFAULT_PROMPT
    prompt = st.text_area("Capture intent", height=120, key="prompt_box")
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if st.button("Load killer demo", type="secondary"):
            st.session_state.prompt_box = DEFAULT_PROMPT
            st.rerun()
    with c2:
        if st.button("Extract Intent Manifest"):
            try:
                session = create_document(prompt or DEFAULT_PROMPT)
                st.session_state.document_id = session["document"]["id"]
                _clear_err()
                st.rerun()
            except Exception as exc:
                _err(exc)

    st.caption("Structured terms are approved before generation. Chat is not authorization.")

    cols = st.columns(3)
    for col, (num, title, body) in zip(
        cols,
        [
            ("01", "Intent Manifest", "Parties, money, notice, renewal, law, and prohibited clauses become the source of truth."),
            ("02", "Semantic checksum", "Formatting may change. An obligation may not. The gate fingerprints meaning, not bytes."),
            ("03", "Human signs", "Foxit eSign is called only after the gate opens. The agent never executes the commitment."),
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


def render_workspace(session: dict) -> None:
    document = session["document"]
    decision = session["decision"]
    extracted = session["extracted"]
    gate = (decision or {}).get("status")

    top_l, top_r = st.columns([4, 1])
    with top_l:
        if st.button("← New request", type="secondary"):
            st.session_state.document_id = None
            st.rerun()
        st.markdown('<p class="sg-kicker">SignGate</p>', unsafe_allow_html=True)
        st.title(document["title"])
        st.write(document["prompt"])
        st.caption(f"{document['id']}  ·  {document['status'].replace('_', ' ')}  ·  {'Foxit connected' if foxit_configured() else 'Local PDF engine'}")
    with top_r:
        if gate == "open":
            color, label = "#0b7a4b", "OPEN"
        elif gate == "blocked":
            color, label = "#b42318", "BLOCKED"
        else:
            color, label = "#6d675c", "CLOSED"
        st.markdown(
            f'<div class="sg-seal" style="color:{color}"><div><div class="sg-kicker">Signature gate</div><div style="font-size:28px;font-family:Times New Roman,serif;margin-top:6px">{label}</div></div></div>',
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

    manifest = session["manifest"]
    approved = session["approved_manifest"]
    locked = bool(approved) and document["status"] != "awaiting_approval"

    st.markdown("### Intent Manifest")
    if approved:
        st.caption(f"Approved v{approved['version']}")
    else:
        st.caption("Awaiting human approval")
    draft = _manifest_editor(manifest["payload"], locked) if manifest else None

    b1, b2, b3, b4 = st.columns(4)
    if draft and not locked and b1.button("Save draft", type="secondary"):
        try:
            update_draft_manifest(document["id"], draft)
            _clear_err()
            st.rerun()
        except Exception as exc:
            _err(exc)
    if b2.button("Approve these terms", disabled=bool(approved) and document["status"] != "awaiting_approval"):
        try:
            if draft and not locked:
                update_draft_manifest(document["id"], draft)
            approve_manifest(document["id"])
            _clear_err()
            st.rerun()
        except Exception as exc:
            _err(exc)
    if b3.button("Generate agreement PDF", disabled=not approved):
        try:
            generate_document(document["id"])
            _clear_err()
            st.rerun()
        except Exception as exc:
            _err(exc)

    left, right = st.columns(2)
    with left:
        st.markdown("### Final document")
        if session["current_version"]:
            st.caption(f"v{session['current_version']['version']} · {session['current_version']['source']}")
            pdf_data = pdf_bytes(document["id"])
            st.download_button(
                "Download PDF",
                data=pdf_data,
                file_name=f"signgate-{document['id']}.pdf",
                mime="application/pdf",
            )
            if hasattr(st, "pdf"):
                st.pdf(pdf_data, height=520)
            else:
                st.caption("PDF preview requires Streamlit 1.49+. Download the file above to review it.")
        else:
            st.info("Approve the manifest, then generate or upload a PDF.")
        uploaded = st.file_uploader("Upload PDF", type=["pdf"])
        if uploaded is not None and st.button("Verify uploaded PDF"):
            try:
                upload_document(document["id"], uploaded.getvalue())
                _clear_err()
                st.rerun()
            except Exception as exc:
                _err(exc)
        u1, u2 = st.columns(2)
        if u1.button("Introduce adversarial edit", disabled=not session["current_version"], type="secondary"):
            try:
                introduce_adversary(document["id"])
                _clear_err()
                st.rerun()
            except Exception as exc:
                _err(exc)
        if u2.button(
            "Restore approved PDF",
            disabled=not any(v["source"] == "generated" for v in session["versions"]),
            type="secondary",
        ):
            try:
                restore_approved(document["id"])
                _clear_err()
                st.rerun()
            except Exception as exc:
                _err(exc)

    with right:
        st.markdown("### Verification")
        st.caption("Exact values, structure, and legal meaning. The LLM may propose findings; it cannot open the gate.")
        if decision:
            st.write(
                f"{decision['verified_term_count']} terms checked · "
                f"{len(decision['missing_attachments'])} missing attachments · "
                f"{len(decision['discrepancies'])} findings"
            )
            if not decision["discrepancies"]:
                st.success("0 material discrepancies. Semantic checksum holds.")
            for item in decision["discrepancies"]:
                color = {
                    "critical": "#b42318",
                    "material": "#9a6700",
                    "uncertain": "#8a6a2f",
                    "clarifying": "#2450c0",
                }.get(item["severity"], "#6d675c")
                page = f" · p.{item['page']}" if item.get("page") else ""
                excerpt = f"<p style='color:#6d675c;font-size:12px'>“{item['excerpt']}”</p>" if item.get("excerpt") else ""
                st.markdown(
                    f"""<div class="sg-finding">
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

    st.markdown("### Human signing handoff")
    if gate == "open":
        st.write("Verification passed. SignGate can now call Foxit eSign. The agent still cannot sign.")
    else:
        st.write("The eSign API is unreachable until the gate opens. This is the product.")
    s1, s2 = st.columns(2)
    if s1.button("Prepare signature request", disabled=gate != "open"):
        try:
            request_signature(document["id"])
            _clear_err()
            st.rerun()
        except Exception as exc:
            _err(exc)
    if session["signature_request"]:
        st.info(
            f"Signing desk ready for {session['approved_manifest']['payload']['signer']['name']}. "
            f"Provider: {session['signature_request']['provider']} · {session['signature_request']['status']}"
        )
        if session["signature_request"]["status"] != "signed":
            if s2.button("I have reviewed the verified document and I sign"):
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
        st.caption("Agents can draft. Humans authorize.")
        st.markdown(
            """
            **Control path**
            1. Capture — prompt → structured terms
            2. Approve — human authorizes the manifest
            3. Generate — PDF from approved terms
            4. Verify — exact, structural, semantic
            5. Handoff — eSign only if the gate is open
            """
        )
        st.caption(
            "Chat is not authorization. The approved Intent Manifest is the source of truth — "
            "not the model’s memory, and not the latest Word file."
        )

    if st.session_state.document_id:
        try:
            render_workspace(get_session(st.session_state.document_id))
        except Exception as exc:
            st.error(str(exc))
            st.session_state.document_id = None
    else:
        render_home()


main()
