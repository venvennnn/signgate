import type { Discrepancy, ExtractedTerms, IntentManifest } from "./types";

const SEMANTIC_PROMPT = `You are a legal-meaning reviewer for SignGate.
The human already approved an Intent Manifest. Compare it to terms extracted from a final PDF.
Propose discrepancies only when the legal meaning changed (obligations, liability, renewal, termination, payment, parties, jurisdiction).
Ignore formatting, punctuation, page reflow, and synonymous wording that does not change obligations.
Do not declare the contract safe. Do not open or close the signature gate.
Return JSON: { "findings": [{ "field": string, "title": string, "severity": "clarifying"|"material"|"critical"|"uncertain", "approved_value": string, "found_value": string, "rationale": string, "confidence": number }] }
If you are not sure, emit severity "uncertain". Empty findings is allowed.`;

export async function proposeSemanticFindings(
  manifest: IntentManifest,
  extracted: ExtractedTerms,
): Promise<{ findings: Discrepancy[]; used: boolean }> {
  const openai = process.env.OPENAI_API_KEY;
  const anthropic = process.env.ANTHROPIC_API_KEY;
  if (!openai && !anthropic) {
    return { findings: [], used: false };
  }

  const user = JSON.stringify(
    {
      approved_manifest: manifest,
      extracted_terms: {
        parties: extracted.parties,
        commercial_terms: extracted.commercial_terms,
        legal_terms: extracted.legal_terms,
        attachments_found: extracted.attachments_found,
        excerpts: extracted.excerpts,
        sample_text: extracted.raw_text.slice(0, 8000),
      },
    },
    null,
    2,
  );

  try {
    const raw = openai ? await callOpenAI(user) : await callAnthropic(user);
    const parsed = JSON.parse(raw) as {
      findings?: Array<{
        field: string;
        title: string;
        severity: Discrepancy["severity"];
        approved_value: string;
        found_value: string;
        rationale: string;
        confidence?: number;
      }>;
    };
    const findings: Discrepancy[] = (parsed.findings ?? []).map((item) => ({
      severity: item.severity,
      layer: "semantic",
      field: item.field,
      title: item.title,
      approved_value: item.approved_value,
      found_value: item.found_value,
      page: extracted.field_pages[item.field] ?? null,
      excerpt: extracted.excerpts[item.field] ?? null,
      rationale: `${item.rationale} (LLM proposal — not independently authoritative.)`,
      confidence: item.confidence ?? 0.6,
    }));
    return { findings, used: true };
  } catch {
    return {
      findings: [
        {
          severity: "uncertain",
          layer: "semantic",
          field: "semantic_review",
          title: "Semantic reviewer failed",
          approved_value: "Deterministic checks still apply",
          found_value: "LLM proposal unavailable",
          page: null,
          excerpt: null,
          rationale: "The language model could not complete a semantic review. The gate stays conservative.",
          confidence: 0.2,
        },
      ],
      used: true,
    };
  }
}

async function callOpenAI(user: string) {
  const res = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: process.env.OPENAI_MODEL || "gpt-4.1-mini",
      temperature: 0,
      response_format: { type: "json_object" },
      messages: [
        { role: "system", content: SEMANTIC_PROMPT },
        { role: "user", content: user },
      ],
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  const body = (await res.json()) as { choices: Array<{ message: { content: string } }> };
  return body.choices[0].message.content;
}

async function callAnthropic(user: string) {
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": process.env.ANTHROPIC_API_KEY || "",
      "anthropic-version": "2023-06-01",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: process.env.ANTHROPIC_MODEL || "claude-sonnet-4-20250514",
      max_tokens: 1200,
      temperature: 0,
      system: SEMANTIC_PROMPT,
      messages: [{ role: "user", content: user }],
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  const body = (await res.json()) as { content: Array<{ text?: string }> };
  const text = body.content.map((part) => part.text ?? "").join("");
  const json = text.match(/\{[\s\S]*\}/)?.[0];
  if (!json) throw new Error("No JSON in Anthropic response");
  return json;
}
