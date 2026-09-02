"use client";

import type { Discrepancy, IntentManifest, SessionSnapshot } from "@/lib/types";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

function statusLabel(status: string) {
  return status.replaceAll("_", " ");
}

function GateSeal({ decision }: { decision: SessionSnapshot["decision"] }) {
  if (!decision) {
    return (
      <div className="seal text-[var(--muted)] border-[var(--muted)]">
        <div>
          <div className="font-[family-name:var(--font-mono)] text-[10px]">GATE</div>
          <div className="mt-1 font-[family-name:var(--font-serif)] text-xl tracking-[0.12em] normal-case">CLOSED</div>
        </div>
      </div>
    );
  }
  const open = decision.status === "open";
  return (
    <div
      className="seal"
      style={{ color: open ? "var(--open)" : "var(--blocked)", borderColor: "currentColor" }}
    >
      <div>
        <div className="font-[family-name:var(--font-mono)] text-[10px]">SIGNATURE GATE</div>
        <div className="mt-1 font-[family-name:var(--font-serif)] text-2xl tracking-[0.08em] normal-case">
          {open ? "OPEN" : "BLOCKED"}
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="font-[family-name:var(--font-mono)] text-[10px] uppercase tracking-[0.18em] text-[#6d675c]">
        {label}
      </span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

const inputCls =
  "w-full border border-[#d8d0c0] bg-white/60 px-3 py-2 text-sm outline-none focus:border-[#8a6a2f]";

function ManifestForm({
  value,
  onChange,
  readOnly,
}: {
  value: IntentManifest;
  onChange: (next: IntentManifest) => void;
  readOnly?: boolean;
}) {
  function patch(path: (draft: IntentManifest) => void) {
    const next = structuredClone(value);
    path(next);
    onChange(next);
  }
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Field label="Customer">
        <input
          className={inputCls}
          readOnly={readOnly}
          value={value.parties.customer}
          onChange={(e) => patch((d) => (d.parties.customer = e.target.value))}
        />
      </Field>
      <Field label="Vendor">
        <input
          className={inputCls}
          readOnly={readOnly}
          value={value.parties.vendor}
          onChange={(e) => patch((d) => (d.parties.vendor = e.target.value))}
        />
      </Field>
      <Field label="Contract value">
        <div className="flex gap-2">
          <input
            className={`${inputCls} w-24`}
            readOnly={readOnly}
            value={value.commercial_terms.contract_value.currency}
            onChange={(e) => patch((d) => (d.commercial_terms.contract_value.currency = e.target.value.toUpperCase()))}
          />
          <input
            className={inputCls}
            readOnly={readOnly}
            type="number"
            value={value.commercial_terms.contract_value.amount}
            onChange={(e) => patch((d) => (d.commercial_terms.contract_value.amount = Number(e.target.value)))}
          />
        </div>
      </Field>
      <Field label="Term (months)">
        <input
          className={inputCls}
          readOnly={readOnly}
          type="number"
          value={value.commercial_terms.term_months}
          onChange={(e) => patch((d) => (d.commercial_terms.term_months = Number(e.target.value)))}
        />
      </Field>
      <Field label="Payment terms (days)">
        <input
          className={inputCls}
          readOnly={readOnly}
          type="number"
          value={value.commercial_terms.payment_terms_days}
          onChange={(e) => patch((d) => (d.commercial_terms.payment_terms_days = Number(e.target.value)))}
        />
      </Field>
      <Field label="Termination notice (days)">
        <input
          className={inputCls}
          readOnly={readOnly}
          type="number"
          value={value.legal_terms.termination_notice_days}
          onChange={(e) => patch((d) => (d.legal_terms.termination_notice_days = Number(e.target.value)))}
        />
      </Field>
      <Field label="Governing law">
        <input
          className={inputCls}
          readOnly={readOnly}
          value={value.legal_terms.governing_law}
          onChange={(e) => patch((d) => (d.legal_terms.governing_law = e.target.value))}
        />
      </Field>
      <Field label="Signer email">
        <input
          className={inputCls}
          readOnly={readOnly}
          value={value.signer.email}
          onChange={(e) => patch((d) => (d.signer.email = e.target.value))}
        />
      </Field>
      <div className="md:col-span-2 flex flex-wrap gap-5 text-sm">
        {[
          ["auto_renewal", "Automatic renewal", value.legal_terms.auto_renewal] as const,
          ["personal_guarantee", "Personal guarantee", value.legal_terms.personal_guarantee] as const,
          ["exclusivity", "Exclusivity", value.legal_terms.exclusivity] as const,
        ].map(([key, label, checked]) => (
          <label key={key} className="flex items-center gap-2">
            <input
              type="checkbox"
              disabled={readOnly}
              checked={checked}
              onChange={(e) =>
                patch((d) => {
                  if (key === "auto_renewal") d.legal_terms.auto_renewal = e.target.checked;
                  if (key === "personal_guarantee") d.legal_terms.personal_guarantee = e.target.checked;
                  if (key === "exclusivity") d.legal_terms.exclusivity = e.target.checked;
                })
              }
            />
            {label}
          </label>
        ))}
      </div>
      <Field label="Required attachments">
        <input
          className={inputCls}
          readOnly={readOnly}
          value={value.required_attachments.join(", ")}
          onChange={(e) =>
            patch((d) => {
              d.required_attachments = e.target.value
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean);
            })
          }
        />
      </Field>
      <Field label="Must not include">
        <input
          className={inputCls}
          readOnly={readOnly}
          value={value.must_not_include.join(", ")}
          onChange={(e) =>
            patch((d) => {
              d.must_not_include = e.target.value
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean);
            })
          }
        />
      </Field>
    </div>
  );
}

function severityColor(severity: Discrepancy["severity"]) {
  switch (severity) {
    case "critical":
      return "#ff4d3a";
    case "material":
      return "#ffb020";
    case "uncertain":
      return "#e4c888";
    case "clarifying":
      return "#8cb4ff";
    default:
      return "#8c887a";
  }
}

export function Workspace({ initial }: { initial: SessionSnapshot }) {
  const [session, setSession] = useState(initial);
  const [draft, setDraft] = useState<IntentManifest | null>(initial.manifest?.payload ?? null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pdfTick, setPdfTick] = useState(0);

  const approved = session.approved_manifest?.status === "approved";
  const manifestLocked = approved && session.document.status !== "awaiting_approval";

  useEffect(() => {
    setDraft(session.manifest?.payload ?? null);
  }, [session.manifest?.id, session.manifest?.payload]);

  const act = useCallback(async (action: string, extra?: Record<string, unknown>) => {
    setBusy(action);
    setError(null);
    try {
      const res = await fetch(`/api/documents/${session.document.id}/actions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, actor: "human:operator", ...extra }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error || "Action failed");
      setSession(body);
      setPdfTick((n) => n + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(null);
    }
  }, [session.document.id]);

  async function saveDraft() {
    if (!draft) return;
    setBusy("save");
    setError(null);
    try {
      const res = await fetch(`/api/documents/${session.document.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ manifest: draft }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error || "Save failed");
      setSession(body);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(null);
    }
  }

  async function upload(file: File) {
    setBusy("upload");
    setError(null);
    try {
      const form = new FormData();
      form.set("file", file);
      const res = await fetch(`/api/documents/${session.document.id}/upload`, { method: "POST", body: form });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error || "Upload failed");
      setSession(body);
      setPdfTick((n) => n + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(null);
    }
  }

  const checksum = useMemo(() => session.decision?.semantic_checksum.slice(0, 16) ?? "————————", [session.decision]);
  const extractedChecksum = session.decision?.extracted_checksum.slice(0, 16) ?? "————————";
  const gateOpen = session.decision?.status === "open";

  return (
    <div className="min-h-screen grid-fine">
      <header className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-[var(--line)]">
        <div className="flex items-baseline gap-3">
          <Link href="/" className="font-[family-name:var(--font-serif)] text-xl">
            SignGate
          </Link>
          <span className="font-[family-name:var(--font-mono)] text-[11px] text-[var(--muted)]">
            {session.document.id} · {statusLabel(session.document.status)}
          </span>
        </div>
        <div className="flex items-center gap-3 font-[family-name:var(--font-mono)] text-[11px] uppercase tracking-[0.16em] text-[var(--muted)]">
          <span>{session.foxit_configured ? "Foxit connected" : "Local PDF engine"}</span>
          <a className="text-[var(--brass)]" href={`/api/documents/${session.document.id}/receipt`}>
            Audit JSON
          </a>
          <a className="text-[var(--brass)]" href={`/api/documents/${session.document.id}/receipt?format=pdf`}>
            Receipt PDF
          </a>
        </div>
      </header>

      <div className="grid xl:grid-cols-[220px_1fr_280px]">
        <aside className="border-b xl:border-b-0 xl:border-r border-[var(--line)] p-5">
          <p className="font-[family-name:var(--font-mono)] text-[10px] uppercase tracking-[0.2em] text-[var(--brass)]">
            Control path
          </p>
          <ol className="mt-4 space-y-4 text-sm">
            {[
              ["Capture", "Prompt → structured terms"],
              ["Approve", "Human authorizes the manifest"],
              ["Generate", "PDF from approved terms"],
              ["Verify", "Exact, structural, semantic"],
              ["Handoff", "eSign only if gate is open"],
            ].map(([title, body], idx) => (
              <li key={title} className="flex gap-3">
                <span className="font-[family-name:var(--font-mono)] text-[var(--brass)]">0{idx + 1}</span>
                <span>
                  <span className="block">{title}</span>
                  <span className="text-[var(--muted)]">{body}</span>
                </span>
              </li>
            ))}
          </ol>
          <div className="mt-8 text-xs leading-relaxed text-[var(--muted)]">
            Chat is not authorization. The approved Intent Manifest is the source of truth — not the model’s memory,
            and not the latest Word file.
          </div>
        </aside>

        <section className="p-5 md:p-8 space-y-6">
          <div>
            <h1 className="font-[family-name:var(--font-serif)] text-4xl">{session.document.title}</h1>
            <p className="mt-2 text-[#cfc8b8]">{session.document.prompt}</p>
          </div>

          {error ? (
            <div className="border border-[var(--blocked)] text-[var(--blocked)] px-4 py-3 text-sm">{error}</div>
          ) : null}

          <div className="paper p-5 md:p-6">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
              <h2 className="font-[family-name:var(--font-serif)] text-2xl">Intent Manifest</h2>
              <span className="font-[family-name:var(--font-mono)] text-[11px] uppercase tracking-widest text-[#6d675c]">
                {approved ? `Approved v${session.approved_manifest?.version}` : "Awaiting human approval"}
              </span>
            </div>
            {draft ? <ManifestForm value={draft} onChange={setDraft} readOnly={manifestLocked} /> : null}
            <div className="mt-5 flex flex-wrap gap-3">
              {!manifestLocked ? (
                <button type="button" className="border border-[#1b1a16] px-4 py-2 text-sm" onClick={saveDraft} disabled={!!busy}>
                  Save draft
                </button>
              ) : null}
              <button
                type="button"
                className="bg-[#1b1a16] text-[var(--paper)] px-4 py-2 text-sm disabled:opacity-50"
                onClick={() => act("approve")}
                disabled={!!busy || (approved && session.document.status !== "awaiting_approval")}
              >
                {busy === "approve" ? "Recording approval…" : "Approve these terms"}
              </button>
              <button
                type="button"
                className="border border-[#1b1a16] px-4 py-2 text-sm disabled:opacity-50"
                onClick={() => act("generate")}
                disabled={!!busy || !approved}
              >
                {busy === "generate" ? "Generating…" : "Generate agreement PDF"}
              </button>
            </div>
          </div>

          <div className="grid lg:grid-cols-2 gap-6">
            <div className="border border-[var(--line)] p-4 min-h-[420px]">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-[family-name:var(--font-serif)] text-xl">Final document</h2>
                {session.current_version ? (
                  <a className="text-xs text-[var(--brass)]" href={`/api/documents/${session.document.id}/pdf`}>
                    v{session.current_version.version} · {session.current_version.source}
                  </a>
                ) : (
                  <span className="text-xs text-[var(--muted)]">No PDF yet</span>
                )}
              </div>
              {session.current_version ? (
                <iframe
                  title="Agreement PDF"
                  className="h-[520px] w-full bg-white"
                  src={`/api/documents/${session.document.id}/pdf?t=${pdfTick}`}
                />
              ) : (
                <div className="h-[520px] grid place-items-center text-[var(--muted)] text-sm">
                  Approve the manifest, then generate or upload a PDF.
                </div>
              )}
              <div className="mt-3 flex flex-wrap gap-2">
                <label className="border border-[var(--line)] px-3 py-2 text-xs cursor-pointer">
                  Upload PDF
                  <input
                    type="file"
                    accept="application/pdf"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) void upload(file);
                      e.currentTarget.value = "";
                    }}
                  />
                </label>
                <button
                  type="button"
                  className="border border-[var(--blocked)] text-[var(--blocked)] px-3 py-2 text-xs disabled:opacity-40"
                  onClick={() => act("adversary")}
                  disabled={!!busy || !session.current_version}
                >
                  {busy === "adversary" ? "Tampering…" : "Introduce adversarial edit"}
                </button>
                <button
                  type="button"
                  className="border border-[var(--line)] px-3 py-2 text-xs disabled:opacity-40"
                  onClick={() => act("restore")}
                  disabled={!!busy || !session.versions.some((v) => v.source === "generated")}
                >
                  Restore approved PDF
                </button>
              </div>
            </div>

            <div className="border border-[var(--line)] p-4">
              <h2 className="font-[family-name:var(--font-serif)] text-xl">Verification</h2>
              <p className="mt-1 text-sm text-[var(--muted)]">
                Exact values, structure, and legal meaning. The LLM may propose findings; it cannot open the gate.
              </p>
              {session.decision ? (
                <div className="mt-4 space-y-3">
                  <p className="font-[family-name:var(--font-mono)] text-xs uppercase tracking-[0.18em] text-[var(--brass)]">
                    {session.decision.verified_term_count} terms checked · {session.decision.missing_attachments.length} missing
                    attachments · {session.decision.discrepancies.length} findings
                  </p>
                  {session.decision.discrepancies.length === 0 ? (
                    <div className="border border-[var(--open)] text-[var(--open)] px-3 py-3 text-sm">
                      0 material discrepancies. Semantic checksum holds.
                    </div>
                  ) : (
                    session.decision.discrepancies.map((item) => (
                      <article key={item.id} className="border border-[var(--line)] p-3">
                        <div className="flex items-center justify-between gap-3">
                          <span
                            className="font-[family-name:var(--font-mono)] text-[10px] uppercase tracking-[0.18em]"
                            style={{ color: severityColor(item.severity) }}
                          >
                            {item.severity} · {item.layer}
                          </span>
                          {item.page ? <span className="text-[11px] text-[var(--muted)]">p.{item.page}</span> : null}
                        </div>
                        <h3 className="mt-1 font-medium">{item.title}</h3>
                        <p className="mt-1 text-sm">
                          <span className="text-[var(--muted)]">Approved</span> {item.approved_value}
                          <span className="text-[var(--muted)]"> → Final </span>
                          {item.found_value}
                        </p>
                        <p className="mt-1 text-xs text-[var(--muted)]">{item.rationale}</p>
                        {item.excerpt ? (
                          <p className="mt-2 font-[family-name:var(--font-mono)] text-[11px] text-[#cfc8b8]">
                            “{item.excerpt}”
                          </p>
                        ) : null}
                      </article>
                    ))
                  )}
                </div>
              ) : (
                <p className="mt-6 text-sm text-[var(--muted)]">Generate or upload a document to run verification.</p>
              )}
            </div>
          </div>

          <div className="border border-[var(--line)] p-5 flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="font-[family-name:var(--font-serif)] text-xl">Human signing handoff</h2>
              <p className="text-sm text-[var(--muted)] max-w-xl">
                {gateOpen
                  ? "Verification passed. SignGate can now call Foxit eSign. The agent still cannot sign."
                  : "The eSign API is unreachable until the gate opens. This is the product."}
              </p>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                className="px-4 py-2 text-sm disabled:opacity-40"
                style={{
                  background: gateOpen ? "var(--open)" : "transparent",
                  color: gateOpen ? "#0b0c0a" : "var(--muted)",
                  border: gateOpen ? "none" : "1px solid var(--line)",
                }}
                disabled={!gateOpen || !!busy}
                onClick={() => act("esign")}
              >
                {busy === "esign" ? "Preparing…" : "Prepare signature request"}
              </button>
              {session.signature_request ? (
                <Link href={`/d/${session.document.id}/sign`} className="border border-[var(--brass)] text-[var(--brass)] px-4 py-2 text-sm">
                  Open signing desk
                </Link>
              ) : null}
            </div>
          </div>

          <div>
            <h2 className="font-[family-name:var(--font-serif)] text-xl">Audit trail</h2>
            <ol className="mt-3 space-y-2">
              {session.audit.map((event) => (
                <li key={event.id} className="grid gap-1 md:grid-cols-[180px_1fr] font-[family-name:var(--font-mono)] text-[11px]">
                  <span className="text-[var(--muted)]">{event.timestamp.replace("T", " ").slice(0, 19)}</span>
                  <span>
                    <span className="text-[var(--brass)]">{event.action}</span> · {event.actor}
                    {event.reason ? <span className="text-[#cfc8b8]"> — {event.reason}</span> : null}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <aside className="border-t xl:border-t-0 xl:border-l border-[var(--line)] p-6 flex flex-col items-center gap-6">
          <GateSeal decision={session.decision} />
          <div className="w-full">
            <p className="font-[family-name:var(--font-mono)] text-[10px] uppercase tracking-[0.2em] text-[var(--muted)]">
              Semantic checksum
            </p>
            <p className="mt-2 font-[family-name:var(--font-mono)] text-sm break-all">{checksum}</p>
            <p className="mt-1 font-[family-name:var(--font-mono)] text-[10px] text-[var(--muted)]">
              extracted {extractedChecksum}
            </p>
            {session.decision && checksum !== extractedChecksum ? (
              <p className="mt-2 text-xs text-[var(--blocked)]">Meaning fingerprint mismatch.</p>
            ) : session.decision ? (
              <p className="mt-2 text-xs text-[var(--open)]">Meaning fingerprint matches.</p>
            ) : null}
          </div>
          {session.extracted ? (
            <dl className="w-full space-y-2 text-sm">
              {[
                ["Value", session.extracted.commercial_terms.contract_value
                  ? `${session.extracted.commercial_terms.contract_value.currency} ${session.extracted.commercial_terms.contract_value.amount.toLocaleString()}`
                  : "—"],
                ["Notice", session.extracted.legal_terms.termination_notice_days != null
                  ? `${session.extracted.legal_terms.termination_notice_days} days`
                  : "—"],
                ["Auto-renew", session.extracted.legal_terms.auto_renewal == null ? "—" : session.extracted.legal_terms.auto_renewal ? "Yes" : "No"],
                ["Law", session.extracted.legal_terms.governing_law ?? "—"],
                ["Guarantee", session.extracted.legal_terms.personal_guarantee == null ? "—" : session.extracted.legal_terms.personal_guarantee ? "Yes" : "No"],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3 border-b border-[var(--line)] pb-2">
                  <dt className="text-[var(--muted)]">{k}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
