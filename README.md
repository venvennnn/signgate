# SignGate

**Agents can draft. Humans authorize. SignGate proves nothing changed in between.**

Foxit left signing out of the agent toolset. That was the correct choice — and it did not go far enough. A bare handoff is still a vulnerability, because humans suffer from review fatigue. If an agent drafts a 40-page document, the signer will assume it is correct.

**The boundary between agent and signer should not be a handoff. It should be a cryptographic and semantic firewall. SignGate is that firewall.**

SignGate is a Streamlit app: authorization integrity for agent-generated vendor agreements. An agent may prepare a document. Foxit eSign is unreachable until the final PDF still matches the Intent Manifest a human approved.

The most dangerous document is not obviously fraudulent. It is almost identical to the approved version, except for one material change: `$50,000` becomes `$500,000`, `30 days` becomes `90 days`, automatic renewal is inserted, or a required Statement of Work disappears. In the winning demo the vendor does not even return a Word file — they return a **scanned image** of the modified contract.

## Run

```bash
python3 -m pip install -r requirements.txt
python3 -m pytest
streamlit run app.py
```

Then open [http://localhost:8501](http://localhost:8501). Use **Load 3-minute demo**.

Deploy on [Streamlit Community Cloud](https://streamlit.io/cloud) by pointing the app at `app.py`.

Optional environment (see `.env.example`):

| Variable | Purpose |
| --- | --- |
| `FOXIT_CLIENT_ID` / `FOXIT_CLIENT_SECRET` | Foxit OCR, Extraction, Document Generation, Combine, eSign |
| `FOXIT_API_HOST` | Defaults to `https://na1.fusion.foxit.com` |
| `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` | Optional Pass 1 JSON extractor. Never opens the gate. |

Without Foxit credentials, the full demo still runs. Pipeline steps are labeled `foxit` or `local`. SignGate never records a Foxit success on a local fallback.

## Foxit toolpath (the win condition)

| Step | Foxit API | What SignGate uses it for |
| --- | --- | --- |
| OCR | `POST /pdf-services/api/documents/analyze/pdf-ocr` | Vendor scan of a tampered contract becomes searchable |
| Extract | `POST /pdf-services/api/documents/convert/pdf-to-text` | Terms pulled from the (OCR'd) PDF |
| Generate | `POST /document-generation/api/GenerateDocumentBase64` | Clean agreement + Verification Certificate from the Intent Manifest |
| Merge | `POST /pdf-services/api/documents/enhance/pdf-combine` | Certificate becomes page 1 of the instrument |
| eSign | `POST /esign/api/v1/folders/createfolder` | Called only after the Signature Gate is OPEN |

HTML→PDF remains a Foxit fallback if Document Generation is unavailable.

## Two-pass semantic checksum

LLMs are bad at exact character matching and numbers. SignGate does not ask a model whether `$50,000` “matches” `$50,000.00`.

1. **LLM pass (semantic).** The model reads Foxit-extracted text and emits strict JSON in the Intent Manifest schema. It is forbidden to declare the contract safe.
2. **Deterministic pass (syntax).** Python compares field-for-field: `if extracted_json["contract_value_amount"] != manifest_json["contract_value_amount"]: gate = BLOCKED`.

If the model hallucinates a match, the parser JSON still disagrees and Python keeps the parser. The model cannot open the gate.

## Verification cover sheet

Before eSign, SignGate generates a one-page **SignGate Verification Certificate** (green check, Intent Manifest hash, five semantic terms, timestamp) and merges it to the front of the contract. The human signer sees proof that the PDF is still the deal they authorized.

## 3-minute demo

| Time | Action |
| --- | --- |
| 0:00–0:30 | Chat: “Make a $50k contract with no auto-renewal.” The Intent Manifest JSON locks. |
| 0:30–1:15 | Act as the vendor. **Sabotage as scanned image** ($50k→$500k, auto-renewal on). |
| 1:15–2:00 | Push to eSign. Screen goes red. Gate **BLOCKED**. The altered clauses are highlighted. |
| 2:00–2:30 | **Revert to Approved Manifest.** Foxit regenerates the clean PDF, merges the certificate, gate turns green. |
| 2:30–3:00 | Foxit eSign is called. Page 1 is the Verification Certificate. A human signs. |

## What it is not

Not a contract-writing chatbot, PDF summarizer, eSign clone, generic legal assistant, or textual diff tool.

Chat is not authorization. The approved Intent Manifest is the source of truth.
