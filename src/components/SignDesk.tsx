"use client";

import { useState } from "react";

export function SignDesk({
  id,
  title,
  signer,
  status,
}: {
  id: string;
  title: string;
  signer: string;
  status: string;
}) {
  const [state, setState] = useState(status);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function sign() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/documents/${id}/actions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "human_sign", actor: `human:${signer}` }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error || "Signing failed");
      setState(body.signature_request?.status ?? "signed");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signing failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen grid place-items-center px-6">
      <div className="paper max-w-xl w-full p-8">
        <p className="font-[family-name:var(--font-mono)] text-[11px] uppercase tracking-[0.22em] text-[#8a6a2f]">
          Human signing desk
        </p>
        <h1 className="mt-3 font-[family-name:var(--font-serif)] text-4xl">Only a person may authorize this.</h1>
        <p className="mt-4 text-[#4a463d] leading-relaxed">
          {title}. The signature gate was already open. This page is the legally meaningful act. An agent can prepare
          the request; it cannot complete it.
        </p>
        <p className="mt-4 text-sm">Signer: {signer}</p>
        {state === "signed" ? (
          <p className="mt-6 text-[#0b7a4b] font-medium">Signed. The audit trail now records a human actor.</p>
        ) : (
          <button
            type="button"
            onClick={sign}
            disabled={busy}
            className="mt-6 bg-[#1b1a16] text-[var(--paper)] px-5 py-3"
          >
            {busy ? "Recording…" : "I have reviewed the verified document and I sign"}
          </button>
        )}
        {error ? <p className="mt-4 text-sm text-[#b42318]">{error}</p> : null}
        <p className="mt-8 text-sm">
          <a href={`/d/${id}`} className="underline">
            Return to SignGate
          </a>
        </p>
      </div>
    </main>
  );
}
