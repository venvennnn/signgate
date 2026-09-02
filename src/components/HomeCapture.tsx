"use client";

import { DEFAULT_PROMPT } from "@/lib/intent";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

type DocRow = { id: string; title: string; status: string; updated_at: string };

export function HomeCapture() {
  const router = useRouter();
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<DocRow[]>([]);

  useEffect(() => {
    fetch("/api/documents")
      .then((res) => res.json())
      .then((body) => setRecent(body.documents ?? []))
      .catch(() => undefined);
  }, []);

  async function capture() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/documents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, actor: "human:operator" }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error || "Failed to capture intent");
      router.push(`/d/${body.document.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
      setBusy(false);
    }
  }

  return (
    <main className="grid-fine min-h-screen">
      <header className="flex items-center justify-between px-6 py-5 border-b border-[var(--line)]">
        <div className="flex items-baseline gap-3">
          <span className="font-[family-name:var(--font-serif)] text-2xl tracking-tight">SignGate</span>
          <span className="font-[family-name:var(--font-mono)] text-[11px] uppercase tracking-[0.22em] text-[var(--brass)]">
            Authorization integrity
          </span>
        </div>
        <p className="hidden md:block font-[family-name:var(--font-mono)] text-[11px] text-[var(--muted)]">
          Agents can draft. Humans authorize.
        </p>
      </header>

      <section className="mx-auto max-w-5xl px-6 py-16 md:py-24">
        <p className="font-[family-name:var(--font-mono)] text-xs uppercase tracking-[0.28em] text-[var(--brass)]">
          The last check before a document becomes legally real
        </p>
        <h1 className="mt-4 max-w-3xl font-[family-name:var(--font-serif)] text-5xl leading-[1.05] md:text-7xl">
          Prove the final PDF is still the deal a human approved.
        </h1>
        <p className="mt-6 max-w-2xl text-lg leading-relaxed text-[#cfc8b8]">
          The most dangerous document is almost identical to the approved version, except for one material change.
          SignGate extracts an Intent Manifest, requires human approval, then blocks eSign if the PDF diverges.
        </p>

        <div className="mt-12 paper rounded-sm p-4 md:p-6 shadow-[0_30px_80px_rgba(0,0,0,0.35)]">
          <div className="flex items-center justify-between gap-4 mb-3">
            <label className="font-[family-name:var(--font-mono)] text-[11px] uppercase tracking-[0.2em] text-[#6d675c]">
              Capture intent
            </label>
            <button
              type="button"
              className="text-[11px] uppercase tracking-[0.16em] text-[#8a6a2f]"
              onClick={() => setPrompt(DEFAULT_PROMPT)}
            >
              Load killer demo
            </button>
          </div>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={4}
            className="w-full resize-none bg-transparent text-lg leading-relaxed outline-none font-[family-name:var(--font-serif)]"
          />
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-[#d8d0c0] pt-4">
            <p className="text-sm text-[#6d675c]">
              Structured terms are approved <em>before</em> generation. Chat is not authorization.
            </p>
            <button
              type="button"
              onClick={capture}
              disabled={busy}
              className="bg-[#1b1a16] text-[var(--paper)] px-5 py-2.5 text-sm tracking-wide hover:bg-black disabled:opacity-50"
            >
              {busy ? "Extracting manifest…" : "Extract Intent Manifest"}
            </button>
          </div>
          {error ? <p className="mt-3 text-sm text-[#b42318]">{error}</p> : null}
        </div>

        <div className="mt-16 grid gap-6 md:grid-cols-3">
          {[
            ["01", "Intent Manifest", "Parties, money, notice, renewal, law, and prohibited clauses become the source of truth."],
            ["02", "Semantic checksum", "Formatting may change. An obligation may not. The gate fingerprints meaning, not bytes."],
            ["03", "Human signs", "Foxit eSign is called only after the gate opens. The agent never executes the commitment."],
          ].map(([n, title, body]) => (
            <article key={n} className="border border-[var(--line)] p-5">
              <p className="font-[family-name:var(--font-mono)] text-[11px] text-[var(--brass)]">{n}</p>
              <h2 className="mt-2 font-[family-name:var(--font-serif)] text-2xl">{title}</h2>
              <p className="mt-2 text-sm leading-relaxed text-[#cfc8b8]">{body}</p>
            </article>
          ))}
        </div>

        {recent.length > 0 ? (
          <div className="mt-16">
            <h2 className="font-[family-name:var(--font-mono)] text-xs uppercase tracking-[0.22em] text-[var(--muted)]">
              Recent instruments
            </h2>
            <ul className="mt-4 divide-y divide-[var(--line)] border-y border-[var(--line)]">
              {recent.map((row) => (
                <li key={row.id}>
                  <a href={`/d/${row.id}`} className="flex items-center justify-between py-3 hover:text-[var(--brass)]">
                    <span>{row.title}</span>
                    <span className="font-[family-name:var(--font-mono)] text-xs uppercase tracking-widest text-[var(--muted)]">
                      {row.status.replaceAll("_", " ")}
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>
    </main>
  );
}
