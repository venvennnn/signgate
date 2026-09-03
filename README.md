# SignGate

**Agents can draft. Humans authorize. SignGate proves nothing changed in between.**

SignGate is a Streamlit app: authorization integrity for agent-generated vendor agreements. An agent may prepare a document. It cannot send that document for signature until the final PDF still matches the Intent Manifest a human approved.

The most dangerous document is not obviously fraudulent. It is almost identical to the approved version, except for one material change: `$50,000` becomes `$500,000`, `30 days` becomes `90 days`, automatic renewal is inserted, or a required Statement of Work disappears.

## Run

```bash
python3 -m pip install -r requirements.txt
python3 -m pytest
streamlit run app.py
```

Then open [http://localhost:8501](http://localhost:8501). Use **Load killer demo**.

Deploy on [Streamlit Community Cloud](https://streamlit.io/cloud) by pointing the app at `app.py`. No Node, no Next.js, no separate API server.

Optional environment (see `.env.example`):

| Variable | Purpose |
| --- | --- |
| `FOXIT_CLIENT_ID` / `FOXIT_CLIENT_SECRET` | Foxit PDF Services and eSign after the gate opens |
| `FOXIT_API_HOST` | Defaults to `https://na1.fusion.foxit.com` |
| `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` | Optional semantic reviewer. Proposals only. |

Without Foxit credentials, the full demo still runs with a local PDF engine and a human signing desk.

## Killer demo

1. Capture the one-year $50,000 / 30-day / no auto-renewal request.
2. Approve the Intent Manifest.
3. Generate the PDF → **SIGNATURE GATE: OPEN**.
4. **Introduce adversarial edit** → **BLOCKED** (value, notice, auto-renewal, missing SOW).
5. Restore the approved PDF, then prepare the signature request. A human signs.

## What it is not

Not a contract-writing chatbot, PDF summarizer, eSign clone, generic legal assistant, or textual diff tool.

Chat is not authorization. The approved Intent Manifest is the source of truth.
