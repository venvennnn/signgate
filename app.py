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
    page_title="SignGate",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Global styles ─────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* ─── reset ─────────────────────────────────────── */
    html, body, [data-testid="stAppViewContainer"],
    [data-testid="stHeader"], [data-testid="stSidebar"],
    [data-testid="stBottom"], .stApp, .main, .block-container {
      background: #ffffff !important; color: #1b1a16;
    }
    [data-testid="stSidebar"] { background: #f9f7f2 !important; border-right: 1px solid #e8e2d5; }
    [data-testid="stToolbar"] { display: none; }
    .block-container { padding-top: 2rem; max-width: 1080px; }

    /* ─── typography ─────────────────────────────────── */
    h1 { font-family: "Times New Roman", Times, serif !important;
         font-size: 2rem !important; color: #1b1a16 !important; margin-bottom: .2rem !important; }
    h2, h3 { font-family: "Times New Roman", Times, serif !important; color: #1b1a16 !important; }
    .kicker { font-size: 11px; letter-spacing: .18em; text-transform: uppercase;
               color: #8a6a2f; font-weight: 700; margin: 0 0 4px; }

    /* ─── step progress bar ──────────────────────────── */
    .steps-row { display: flex; gap: 0; margin-bottom: 2rem; border: 1px solid #e8e2d5; }
    .step-cell { flex: 1; padding: .65rem .5rem; text-align: center;
                 font-size: 11px; letter-spacing: .1em; text-transform: uppercase;
                 border-right: 1px solid #e8e2d5; }
    .step-cell:last-child { border-right: none; }
    .step-cell.done { background: #f0faf4; color: #0b7a4b; font-weight: 700; }
    .step-cell.active { background: #1b1a16; color: #fff; font-weight: 700; }
    .step-cell.todo { background: #fff; color: #a09a90; }

    /* ─── gate seal ──────────────────────────────────── */
    .gate-wrap { text-align: center; padding: 1.4rem 1rem 1rem; }
    .gate-circle {
      width: 140px; height: 140px; border-radius: 50%;
      display: inline-flex; align-items: center; justify-content: center;
      flex-direction: column; border-width: 6px; border-style: double; font-weight: 800;
    }
    .gate-open  { color: #0b7a4b; border-color: #0b7a4b; background: #f0faf4; }
    .gate-blocked { color: #b42318; border-color: #b42318; background: #fff5f4; }
    .gate-closed  { color: #6d675c; border-color: #b8b2a8; background: #f9f7f2; }
    .gate-label { font-size: 1.1rem; letter-spacing: .12em; margin-top: 4px; }
    .gate-sub   { font-size: 10px; letter-spacing: .18em; text-transform: uppercase; }

    /* ─── manifest card ──────────────────────────────── */
    .mf-card { border: 1px solid #e8e2d5; padding: 1.2rem 1.4rem; margin-bottom: 1rem; }
    .mf-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: .6rem 1.4rem;
               margin-top: .8rem; }
    .mf-item { }
    .mf-label { font-size: 11px; letter-spacing: .1em; text-transform: uppercase; color: #8a6a2f; }
    .mf-value { font-size: 1.05rem; font-weight: 600; color: #1b1a16; }
    .mf-value.changed { color: #b42318; }
    .locked-badge { display: inline-block; background: #0b7a4b; color: #fff;
                    font-size: 10px; letter-spacing: .2em; padding: 3px 9px;
                    font-weight: 700; margin-left: 8px; vertical-align: middle; }
    .hash-line { font-family: monospace; font-size: 11px; color: #8a6a2f;
                 margin-top: .4rem; word-break: break-all; }

    /* ─── blocked banner ─────────────────────────────── */
    .blocked-banner {
      border: 2px solid #b42318; background: #fff5f4;
      padding: 1.2rem 1.4rem; margin-bottom: 1.4rem;
      animation: blink 0.7s ease 0s 5;
    }
    @keyframes blink {
      0%, 100% { box-shadow: 0 0 0 0 rgba(180,35,24,0); }
      50%       { box-shadow: 0 0 14px 2px rgba(180,35,24,.16); }
    }
    .blocked-banner h3 { color: #b42318 !important; margin: 0 0 .3rem; font-size: 1.2rem !important; }

    /* ─── findings ───────────────────────────────────── */
    .finding { border-left: 4px solid; padding: .75rem 1rem; margin-bottom: .7rem; }
    .finding.critical { border-color: #b42318; background: #fff8f7; }
    .finding.material { border-color: #c67300; background: #fffbf4; }
    .finding.uncertain { border-color: #8a6a2f; background: #fbf8f2; }
    .finding-head { font-size: 10px; letter-spacing: .14em; text-transform: uppercase;
                    font-weight: 700; margin-bottom: 3px; }
    .finding-title { font-size: 1rem; font-weight: 700; margin-bottom: 2px; }
    .finding-diff { font-size: .92rem; color: #444; }
    .finding-diff .was { color: #0b7a4b; }
    .finding-diff .now { color: #b42318; font-weight: 700; }

    /* ─── toolpath chips ─────────────────────────────── */
    .toolpath { display: flex; gap: .5rem; flex-wrap: wrap; margin: .5rem 0 1.2rem; align-items: center; }
    .tp-chip { display: inline-flex; flex-direction: column; align-items: center;
               border: 1px solid; border-radius: 3px; padding: 5px 10px; min-width: 72px; text-align: center; }
    .tp-chip.foxit  { border-color: #0b7a4b; background: #f0faf4; color: #0b7a4b; }
    .tp-chip.local  { border-color: #c67300; background: #fffbf4; color: #c67300; }
    .tp-chip.pending { border-color: #d4cfc8; background: #f9f7f2; color: #a09a90; }
    .tp-chip-name { font-size: 10px; letter-spacing: .1em; text-transform: uppercase; font-weight: 700; }
    .tp-chip-badge { font-size: 10px; margin-top: 2px; }
    .tp-arrow { color: #b8b2a8; font-size: 1rem; }

    /* ─── open banner ────────────────────────────────── */
    .open-banner { border: 2px solid #0b7a4b; background: #f0faf4;
                   padding: 1rem 1.4rem; margin-bottom: 1.2rem; }
    .open-banner h3 { color: #0b7a4b !important; margin: 0 0 .2rem; font-size: 1.15rem !important; }

    /* ─── action area ────────────────────────────────── */
    .action-label { font-size: 11px; letter-spacing: .14em; text-transform: uppercase;
                    color: #8a6a2f; font-weight: 700; margin-bottom: .5rem; }

    /* ─── signed banner ──────────────────────────────── */
    .signed-banner { border: 2px solid #0b7a4b; background: #f0faf4;
                     padding: 1rem 1.4rem; text-align: center; }

    /* ─── buttons ────────────────────────────────────── */
    .stButton>button {
      border-radius: 2px; border: 1.5px solid #1b1a16;
      background: #1b1a16; color: #fff; font-weight: 600;
    }
    .stButton>button:hover { background: #000; border-color: #000; }
    .stButton>button[kind="secondary"] { background: #fff !important; color: #1b1a16 !important; }
    textarea, input, [data-baseweb="input"] { background: #fff !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Constants ──────────────────────────────────────────────────────────────────
ARGUMENT = (
    "Foxit deliberately left signing out of the agent's toolset — that was the right call. "
    "But a bare handoff is still a vulnerability: humans suffer from review fatigue. "
    "The boundary between agent and signer must be a cryptographic and semantic firewall. "
    "SignGate is that firewall."
)

STEPS = ["1 · Capture", "2 · Approve", "3 · Generate", "4 · Verify", "5 · eSign"]

# ── Session state ──────────────────────────────────────────────────────────────
if "document_id" not in st.session_state:
    st.session_state.document_id = None
if "error" not in st.session_state:
    st.session_state.error = None
if "show_advanced" not in st.session_state:
    st.session_state.show_advanced = False


def _err(exc: Exception) -> None:
    st.session_state.error = str(exc)


def _clear_err() -> None:
    st.session_state.error = None


# ── Step tracker ───────────────────────────────────────────────────────────────
def _step_index(status: str) -> int:
    if status in {"draft_intent", "awaiting_approval"}:
        return 1
    if status == "approved":
        return 2
    if status in {"generated", "verified_open", "verified_blocked"}:
        return 3
    if status == "sent_for_signature":
        return 4
    return 0


def _steps_bar(active_idx: int) -> None:
    cells = ""
    for i, label in enumerate(STEPS):
        if i < active_idx:
            klass = "done"
        elif i == active_idx:
            klass = "active"
        else:
            klass = "todo"
        cells += f'<div class="step-cell {klass}">{label}</div>'
    st.markdown(f'<div class="steps-row">{cells}</div>', unsafe_allow_html=True)


# ── Gate seal ──────────────────────────────────────────────────────────────────
def _gate_seal(gate: str | None, checksum: str | None = None) -> None:
    if gate == "open":
        klass, icon, label = "gate-open", "✓", "OPEN"
    elif gate == "blocked":
        klass, icon, label = "gate-blocked", "✕", "BLOCKED"
    else:
        klass, icon, label = "gate-closed", "—", "CLOSED"
    chk = f'<div style="font-family:monospace;font-size:9px;margin-top:6px;opacity:.6">{checksum[:12]}…</div>' if checksum else ""
    st.markdown(
        f"""<div class="gate-wrap">
          <div class="gate-circle {klass}">
            <div style="font-size:2rem;line-height:1">{icon}</div>
            <div class="gate-label">{label}</div>
            <div class="gate-sub">Signature gate</div>
          </div>
          {chk}
        </div>""",
        unsafe_allow_html=True,
    )


# ── Manifest summary card ──────────────────────────────────────────────────────
def _manifest_card(payload: dict, approved: bool, version: int | None = None) -> None:
    value = payload["commercial_terms"]["contract_value"]
    money = f"{value['currency']} {value['amount']:,}"
    badge = f'<span class="locked-badge">LOCKED v{version}</span>' if approved else ""
    auto = "Yes" if payload["legal_terms"]["auto_renewal"] else "No"
    guarantee = "Yes" if payload["legal_terms"]["personal_guarantee"] else "No"
    excl = "Yes" if payload["legal_terms"]["exclusivity"] else "No"
    attach = ", ".join(payload["required_attachments"]) or "None"
    items = [
        ("Customer", payload["parties"]["customer"]),
        ("Vendor", payload["parties"]["vendor"]),
        ("Contract value", money),
        ("Term", f"{payload['commercial_terms']['term_months']} months"),
        ("Payment terms", f"{payload['commercial_terms']['payment_terms_days']} days"),
        ("Termination notice", f"{payload['legal_terms']['termination_notice_days']} days"),
        ("Auto-renewal", auto),
        ("Personal guarantee", guarantee),
        ("Exclusivity", excl),
        ("Governing law", payload["legal_terms"]["governing_law"]),
        ("Required attachments", attach),
        ("Signer", f"{payload['signer']['name']} &lt;{payload['signer']['email']}&gt;"),
    ]
    grid = "".join(
        f'<div class="mf-item"><div class="mf-label">{lbl}</div>'
        f'<div class="mf-value">{val}</div></div>'
        for lbl, val in items
    )
    st.markdown(
        f'<div class="mf-card"><p class="kicker">Intent Manifest {badge}</p>'
        f'<div class="mf-grid">{grid}</div></div>',
        unsafe_allow_html=True,
    )


# ── Toolpath chips ─────────────────────────────────────────────────────────────
_TOOLS = [
    ("ocr", "OCR"),
    ("extract", "Extract"),
    ("generate", "Generate"),
    ("cover_sheet", "Certificate"),
    ("merge", "Merge"),
    ("esign", "eSign"),
]


def _toolpath(pipeline: list) -> None:
    by_tool = {s["tool"]: s for s in (pipeline or [])}
    chips = ""
    for i, (tool, label) in enumerate(_TOOLS):
        step = by_tool.get(tool)
        if not step:
            klass, badge = "pending", "pending"
        elif step["provider"] == "foxit" and step["status"] == "ok":
            klass, badge = "foxit", "Foxit ✓"
        elif step["status"] in {"fallback", "ok"}:
            klass, badge = "local", "local"
        else:
            klass, badge = "pending", step["status"]
        chips += (
            f'<div class="tp-chip {klass}">'
            f'<span class="tp-chip-name">{label}</span>'
            f'<span class="tp-chip-badge">{badge}</span></div>'
        )
        if i < len(_TOOLS) - 1:
            chips += '<span class="tp-arrow">→</span>'
    st.markdown(f'<div class="toolpath">{chips}</div>', unsafe_allow_html=True)


# ── Findings ───────────────────────────────────────────────────────────────────
def _findings(decision: dict) -> None:
    discrepancies = decision.get("discrepancies") or []
    if not discrepancies:
        st.markdown(
            '<div class="open-banner"><h3>✓ All terms verified</h3>'
            '<p style="margin:0">Every canonical field matches the approved Intent Manifest. '
            'Cover sheet is eligible.</p></div>',
            unsafe_allow_html=True,
        )
        return
    for item in discrepancies:
        sev = item.get("severity", "uncertain")
        color_map = {"critical": "#b42318", "material": "#c67300", "uncertain": "#8a6a2f"}
        color = color_map.get(sev, "#6d675c")
        klass = sev if sev in {"critical", "material"} else "uncertain"
        page = f" · p.{item['page']}" if item.get("page") else ""
        was = item.get("approved_value", "")
        now = item.get("found_value", "")
        st.markdown(
            f"""<div class="finding {klass}">
              <div class="finding-head" style="color:{color}">{sev.upper()} · {item.get("layer","").upper()}{page}</div>
              <div class="finding-title">{item.get("title","")}</div>
              <div class="finding-diff">
                Approved <span class="was">{was}</span> &nbsp;→&nbsp; Found <span class="now">{now}</span>
              </div>
            </div>""",
            unsafe_allow_html=True,
        )


# ── Homepage ───────────────────────────────────────────────────────────────────
def render_home() -> None:
    st.markdown('<p class="kicker">Authorization integrity for AI-generated contracts</p>', unsafe_allow_html=True)
    st.title("Agents draft. Humans authorize.\nSignGate proves nothing changed.")

    # Argument
    st.markdown(
        f'<div style="border-left:4px solid #8a6a2f;background:#fbf8f2;padding:.9rem 1.2rem;margin:1rem 0 1.6rem">'
        f'<p class="kicker">The argument</p><p style="margin:0">{ARGUMENT}</p></div>',
        unsafe_allow_html=True,
    )

    # How it works — 5 clear steps
    st.markdown("#### How the 3-minute demo works")
    step_html = "".join(
        f'<div style="flex:1;border:1px solid #e8e2d5;padding:.9rem 1rem;margin-right:.5rem">'
        f'<p class="kicker">{n}</p><strong style="font-size:.95rem">{t}</strong>'
        f'<p style="font-size:.85rem;color:#5a5550;margin:.4rem 0 0">{d}</p></div>'
        for n, t, d in [
            ("0:00", "Lock the terms", "Describe the deal in plain language. The Intent Manifest JSON locks."),
            ("0:30", "Approve & generate", "Human approves the manifest. Foxit DocGen renders the PDF."),
            ("0:45", "Sabotage (scanned image)", "Vendor returns a scan with $50k → $500k and auto-renewal on."),
            ("1:15", "Gate BLOCKED", "Foxit OCR + extract + two-pass Python check. eSign unreachable."),
            ("2:00", "Revert → OPEN → eSign", "Foxit regenerates, merges a Verification Certificate, gate opens, eSign called."),
        ]
    )
    st.markdown(f'<div style="display:flex;gap:.3rem;margin-bottom:1.6rem">{step_html}</div>', unsafe_allow_html=True)

    # CTA
    st.markdown('<p class="kicker">Start the demo</p>', unsafe_allow_html=True)
    if "prompt_box" not in st.session_state:
        st.session_state.prompt_box = DEFAULT_PROMPT
    load_btn, lock_btn, _ = st.columns([1.2, 1.5, 3])
    load_clicked = load_btn.button("↺  Load demo", type="secondary")
    lock_clicked = lock_btn.button("→  Lock Intent Manifest", key="extract_intent")
    if load_clicked:
        st.session_state.prompt_box = DEFAULT_PROMPT
    prompt = st.text_area(
        "Describe the deal",
        height=90,
        key="prompt_box",
        help="Plain language is fine. The system extracts structured terms from it.",
    )
    if lock_clicked:
        try:
            session = create_document(prompt or DEFAULT_PROMPT)
            st.session_state.document_id = session["document"]["id"]
            _clear_err()
            st.rerun()
        except Exception as exc:
            _err(exc)
    if st.session_state.error:
        st.error(st.session_state.error)

    # Recent
    recent = list_documents()
    if recent:
        st.markdown("---")
        st.markdown("**Recent instruments**")
        for row in recent[:6]:
            status_label = row["status"].replace("_", " ")
            icon = "🟢" if "open" in status_label else ("🔴" if "blocked" in status_label else "⚪")
            if st.button(
                f"{icon}  {row['title']}  ·  {status_label}",
                key=f"open-{row['id']}",
                type="secondary",
            ):
                st.session_state.document_id = row["id"]
                _clear_err()
                st.rerun()


# ── Workspace ──────────────────────────────────────────────────────────────────
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
    draft["legal_terms"]["auto_renewal"] = x.checkbox(
        "Automatic renewal", value=draft["legal_terms"]["auto_renewal"], disabled=locked
    )
    draft["legal_terms"]["personal_guarantee"] = y.checkbox(
        "Personal guarantee", value=draft["legal_terms"]["personal_guarantee"], disabled=locked
    )
    draft["legal_terms"]["exclusivity"] = z.checkbox(
        "Exclusivity", value=draft["legal_terms"]["exclusivity"], disabled=locked
    )
    draft["required_attachments"] = [
        p.strip()
        for p in st.text_input(
            "Required attachments", ", ".join(draft["required_attachments"]), disabled=locked
        ).split(",")
        if p.strip()
    ]
    draft["must_not_include"] = [
        p.strip()
        for p in st.text_input(
            "Must not include", ", ".join(draft["must_not_include"]), disabled=locked
        ).split(",")
        if p.strip()
    ]
    return draft


def render_workspace(session: dict) -> None:
    document = session["document"]
    decision = session["decision"]
    manifest = session["manifest"]
    approved = session["approved_manifest"]
    gate = (decision or {}).get("status")
    status = document["status"]
    step_idx = _step_index(status)

    # ── header row ──
    hdr_l, hdr_r = st.columns([5, 2])
    with hdr_l:
        if st.button("← Back", type="secondary", key="back_btn"):
            st.session_state.document_id = None
            st.rerun()
        st.markdown('<p class="kicker">SignGate · authorization integrity</p>', unsafe_allow_html=True)
        st.markdown(f"# {document['title']}")
        mode = "Foxit connected" if foxit_configured() else "Local engine (Foxit fallback)"
        st.caption(f"{document['id']}  ·  {mode}")
    with hdr_r:
        chk = (decision or {}).get("semantic_checksum")
        _gate_seal(gate, chk)

    # ── step bar ──
    _steps_bar(step_idx)

    if st.session_state.error:
        st.error(st.session_state.error)
        st.session_state.error = None

    # ─────────────────────────────────────────────────────────────────
    # STEP 1 — Capture (manifest not yet approved)
    # ─────────────────────────────────────────────────────────────────
    if status in {"awaiting_approval"}:
        st.markdown("## Step 2 · Review and approve the Intent Manifest")
        st.caption("The agent extracted these structured terms from your plain-language request. **You** decide whether they are correct — then approve them as the source of truth.")

        locked = False
        draft = _manifest_editor(manifest["payload"], locked) if manifest else None

        st.markdown("---")
        st.markdown('<p class="action-label">Actions for this step</p>', unsafe_allow_html=True)
        col_save, col_approve, _ = st.columns([1, 1.4, 3])
        if draft and col_save.button("Save edits", type="secondary", key="save_draft"):
            try:
                update_draft_manifest(document["id"], draft)
                _clear_err()
                st.rerun()
            except Exception as exc:
                _err(exc)
        if col_approve.button("✓  Approve these terms", key="approve_terms"):
            try:
                if draft:
                    update_draft_manifest(document["id"], draft)
                approve_manifest(document["id"])
                _clear_err()
                st.rerun()
            except Exception as exc:
                _err(exc)
        st.caption("Approval locks the manifest. Nothing downstream can change it without a new human approval.")

    # ─────────────────────────────────────────────────────────────────
    # STEP 2 — Approved, need to generate
    # ─────────────────────────────────────────────────────────────────
    elif status == "approved":
        st.markdown("## Step 3 · Generate the agreement PDF")
        st.caption("The approved Intent Manifest is now the source of truth. Foxit Document Generation renders the clean PDF from it.")

        if approved:
            _manifest_card(approved["payload"], approved=True, version=approved["version"])

        st.markdown('<p class="action-label">Actions for this step</p>', unsafe_allow_html=True)
        col_gen, _ = st.columns([1.5, 4])
        if col_gen.button("→  Generate agreement PDF", key="generate_pdf"):
            try:
                generate_document(document["id"])
                _clear_err()
                st.rerun()
            except Exception as exc:
                _err(exc)

    # ─────────────────────────────────────────────────────────────────
    # STEP 3/4 — Generated / Verified (the main demo area)
    # ─────────────────────────────────────────────────────────────────
    elif status in {"generated", "verified_open", "verified_blocked"}:
        # Foxit toolpath — always visible
        st.markdown('<p class="kicker">Foxit toolpath</p>', unsafe_allow_html=True)
        _toolpath(session.get("pipeline") or [])

        # Gate result
        if gate == "blocked":
            altered = [i for i in (decision or {}).get("discrepancies", [])
                       if i.get("severity") in {"critical", "material"}]
            names = "  ·  ".join(i["title"] for i in altered[:3]) or "material changes detected"
            st.markdown(
                f'<div class="blocked-banner">'
                f'<h3>✕  SIGNATURE GATE BLOCKED</h3>'
                f'<p style="margin:0;font-size:.95rem">eSign was not called. Altered clauses: <strong>{names}</strong></p>'
                f'</div>',
                unsafe_allow_html=True,
            )
            _findings(decision)

        elif gate == "open":
            st.markdown(
                '<div class="open-banner"><h3>✓  SIGNATURE GATE OPEN</h3>'
                '<p style="margin:0">All terms verified. Cover sheet is eligible. eSign can proceed.</p></div>',
                unsafe_allow_html=True,
            )
            _findings(decision)

        # Manifest summary
        if approved:
            _manifest_card(approved["payload"], approved=True, version=approved["version"])

        # Action buttons grouped
        st.markdown("---")
        st.markdown('<p class="action-label">Demo actions</p>', unsafe_allow_html=True)

        has_version = bool(session["current_version"])
        col_a, col_b, col_c = st.columns(3)

        if col_a.button(
            "🔴  Sabotage — scanned image",
            disabled=not has_version,
            type="secondary",
            key="adversary_scan",
            help="Simulates the vendor returning a scanned image of a tampered contract",
        ):
            try:
                introduce_scanned_adversary(document["id"])
                _clear_err()
                st.rerun()
            except Exception as exc:
                _err(exc)

        if col_b.button(
            "🟢  Revert to approved manifest",
            disabled=not approved,
            key="restore_pdf",
            help="Foxit regenerates the clean PDF from the locked manifest, merges the certificate",
        ):
            try:
                restore_approved(document["id"])
                _clear_err()
                st.rerun()
            except Exception as exc:
                _err(exc)

        col_c.button(
            "🔴  Sabotage — text PDF",
            disabled=not has_version,
            type="secondary",
            key="adversary_text",
            help="Simulates a directly modified text PDF",
            on_click=lambda: (
                introduce_adversary(document["id"]),
                st.rerun(),
            ) if has_version else None,
        )

        # Download + upload
        st.markdown("---")
        dl_col, up_col = st.columns(2)
        if has_version:
            dl_col.download_button(
                "⬇  Download PDF (cover sheet is page 1 if gate is open)",
                data=pdf_bytes(document["id"]),
                file_name=f"signgate-{document['id']}.pdf",
                mime="application/pdf",
                key="dl_pdf",
            )
        with up_col:
            uploaded = st.file_uploader(
                "Upload a vendor scan to verify",
                type=["pdf", "png", "jpg", "jpeg"],
                key="upload_pdf",
                label_visibility="collapsed",
            )
            if uploaded and st.button("Verify this file", key="verify_upload"):
                try:
                    payload = wrap_upload_as_scan(uploaded.getvalue(), uploaded.name)
                    is_scan = not uploaded.name.lower().endswith(".pdf") or "scan" in uploaded.name.lower()
                    upload_document(
                        document["id"], payload,
                        source="uploaded_scan" if is_scan else "uploaded",
                        scan=is_scan,
                    )
                    _clear_err()
                    st.rerun()
                except Exception as exc:
                    _err(exc)

        # Advanced: two-pass + raw JSON (collapsed by default)
        with st.expander("Advanced: two-pass checksum detail"):
            two = (decision or {}).get("two_pass") or {}
            mismatches = (two.get("parser_mismatches") or []) + (two.get("llm_mismatches") or [])
            if mismatches:
                st.error("Pass 2 blocked: " + ", ".join(f"{m['field']}" for m in mismatches))
            else:
                st.success("Pass 2 clear: all canonical fields match the approved manifest.")
            a, b, c = st.columns(3)
            a.json({"approved": two.get("approved_json")})
            b.json({"pass_1_parser": two.get("parser_json")})
            c.json({"pass_1_llm": two.get("llm_json") or {"info": "LLM not configured — parser JSON used"}})

        with st.expander("Advanced: pipeline log"):
            for step in (session.get("pipeline") or []):
                st.caption(f"{step['seq']:02d} · {step['tool']} · {step['provider']}/{step['status']} — {step['detail']}")

    # ─────────────────────────────────────────────────────────────────
    # STEP 4 — eSign handoff
    # ─────────────────────────────────────────────────────────────────
    if status in {"verified_open", "generated"} and gate == "open" and not session["signature_request"]:
        st.markdown("---")
        st.markdown("## Step 5 · Human signing handoff")
        st.caption("The gate is open. SignGate will merge the Verification Certificate and call Foxit eSign. The agent cannot sign.")

        if approved:
            signer = approved["payload"]["signer"]
            st.markdown(
                f'<div style="border:1px solid #e8e2d5;padding:.8rem 1.2rem;display:inline-block">'
                f'<p class="kicker">Signer</p>'
                f'<strong>{signer["name"]}</strong> · {signer["title"]} · {signer["email"]}'
                f'</div>',
                unsafe_allow_html=True,
            )
        esign_col, _ = st.columns([1.6, 4])
        if esign_col.button("→  Prepare signature request (Foxit eSign)", key="prepare_esign"):
            try:
                request_signature(document["id"])
                _clear_err()
                st.rerun()
            except Exception as exc:
                _err(exc)

    if status == "sent_for_signature":
        st.markdown("---")
        st.markdown("## Step 5 · Signing in progress")
        sig = session["signature_request"]
        ap = session["approved_manifest"]
        if sig and ap:
            signer_name = ap["payload"]["signer"]["name"]
            if sig["status"] != "signed":
                st.markdown(
                    f'<div class="open-banner">'
                    f'<h3>Signing desk ready for {signer_name}</h3>'
                    f'<p style="margin:.3rem 0 0">Provider: <strong>{sig["provider"]}</strong> · '
                    f'Ref: {sig["provider_ref"]} · Page 1 is the SignGate Verification Certificate.</p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                sign_col, _ = st.columns([2, 4])
                if sign_col.button(
                    "I have reviewed the verified document — I sign",
                    key="human_sign",
                    type="secondary",
                ):
                    try:
                        complete_human_signature(document["id"], actor=f"human:{signer_name}")
                        _clear_err()
                        st.rerun()
                    except Exception as exc:
                        _err(exc)
            else:
                st.markdown(
                    f'<div class="signed-banner">'
                    f'<h3 style="color:#0b7a4b!important">✓ Signed by {signer_name}</h3>'
                    f'<p style="margin:.3rem 0 0">The audit trail records the human actor. The agent did not sign.</p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # ── Audit trail (always at the bottom, collapsed) ──
    if session.get("audit"):
        receipt_pdf, receipt_json = build_receipt(document["id"])
        with st.expander(f"Audit trail ({len(session['audit'])} events)"):
            for event in session["audit"]:
                st.caption(
                    f"{event['timestamp'][:19].replace('T', ' ')}  ·  "
                    f"{event['action']}  ·  {event['actor']}"
                    + (f" — {event['reason'][:80]}" if event.get("reason") else "")
                )
            a_col, b_col = st.columns(2)
            a_col.download_button(
                "Download audit JSON",
                data=json.dumps(receipt_json, indent=2),
                file_name=f"signgate-{document['id']}.json",
                key="dl_audit_json",
            )
            b_col.download_button(
                "Download audit receipt PDF",
                data=receipt_pdf,
                file_name=f"signgate-receipt-{document['id']}.pdf",
                key="dl_receipt",
            )


# ── Sidebar ────────────────────────────────────────────────────────────────────
def _sidebar() -> None:
    with st.sidebar:
        st.markdown("### SignGate")
        st.caption("Agents draft. Humans authorize. SignGate is the firewall.")
        st.markdown("---")
        st.markdown(
            """
**3-minute demo sequence**

1. **0:00** — Type or load the $50k deal. Lock the manifest.
2. **0:30** — Approve → Generate (Foxit DocGen).
3. **0:45** — Click **Sabotage – scanned image**.
4. **1:15** — Foxit OCR + extract. Gate goes **red**. eSign is unreachable.
5. **2:00** — Click **Revert to approved manifest**. Foxit regenerates + merges certificate.
6. **2:30** — Gate **green**. Foxit eSign. Cover sheet is page 1.
"""
        )
        st.markdown("---")
        st.caption(ARGUMENT)


# ── Entry point ────────────────────────────────────────────────────────────────
def main() -> None:
    _sidebar()
    if st.session_state.document_id:
        try:
            render_workspace(get_session(st.session_state.document_id))
        except Exception as exc:
            st.session_state.document_id = None
            st.error(f"Session error: {exc}")
            st.rerun()
    else:
        render_home()


main()
