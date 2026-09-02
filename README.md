# SignGate

**Agents can draft. Humans authorize. SignGate proves nothing changed in between.**

SignGate is authorization integrity infrastructure for agent-generated documents. An agent may prepare a vendor agreement. It cannot send that agreement for signature until the final PDF still matches the Intent Manifest a human approved.

The most dangerous document is not obviously fraudulent. It is almost identical to the approved version, except for one material change: `$50,000` becomes `$500,000`, `30 days` becomes `90 days`, automatic renewal is inserted, or a required Statement of Work disappears.

## What it is not

Not a contract-writing chatbot, PDF summarizer, eSign clone, generic legal assistant, or textual diff tool.

Ordinary document agents optimize for completion. SignGate optimizes for authorization integrity.

## The gate

1. **Capture intent** from a plain-language request into a structured Intent Manifest.
2. **Human approval** of those terms — chat is not authorization.
3. **Generate or upload** a PDF (Foxit HTML→PDF when credentials exist; local engine otherwise).
4. **Verify** exact values, structure, and legal meaning against the approved manifest.
5. **Classify** cosmetic / clarifying / material / critical / uncertain.
6. **Block or open** the signature gate. Material, critical, or uncertain findings close it.
7. **Call Foxit eSign only when open.** The agent prepares the request. A human signs.
8. **Export an audit receipt** of every actor, hash, manifest version, and state change.

The LLM may propose semantic findings. It must not independently declare a contract safe. Deterministic parsers and human authorization control the gate.

## Killer demo

```
Create a one-year data-services agreement for $50,000, with 30-day termination and no automatic renewal.
```

Approve the extracted manifest, generate the PDF, and the gate opens.

Then click **Introduce adversarial edit**:

- contract value → USD 500,000
- termination notice → 90 days
- automatic renewal inserted
- Statement of Work removed

The gate blocks. Restore the approved PDF, or explicitly approve a new Intent Manifest.

## Run

```bash
npm install
npm test
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

Optional environment (see `.env.example`):

| Variable | Purpose |
| --- | --- |
| `FOXIT_CLIENT_ID` / `FOXIT_CLIENT_SECRET` | Foxit PDF Services (HTML→PDF, text extract) and eSign after the gate opens |
| `FOXIT_API_HOST` | Defaults to `https://na1.fusion.foxit.com` |
| `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` | Optional semantic reviewer. Proposals only. |

Without Foxit credentials, SignGate still runs the full demo with a local PDF engine and a human signing desk.

## Architecture

| Component | Responsibility |
| --- | --- |
| Frontend | Intent capture, term approval, comparison, gate status |
| Orchestrator | Prompt → manifest, generate/upload, verify, eSign handoff |
| Foxit adapter | PDF Services + eSign when configured |
| Verification engine | Exact, structural, and semantic checks |
| SQLite audit store | Manifests, versions, findings, gate decisions, actors |

Data lives in `data/signgate.db` and `data/files/`.

Hackathon scope is one document type: a vendor / data-services agreement. That is intentional.
