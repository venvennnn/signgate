from __future__ import annotations

import json
import os
from typing import Any

import requests

from .types import ExtractedTerms, IntentManifest

PROMPT = """You extract structured contract terms from OCR/extracted PDF text.
Return ONLY JSON matching this schema:
{
  "contract_value_amount": number,
  "contract_value_currency": "USD"|"SGD"|"EUR"|"GBP",
  "term_months": number,
  "payment_terms_days": number,
  "termination_notice_days": number,
  "auto_renewal": boolean,
  "personal_guarantee": boolean,
  "exclusivity": boolean,
  "governing_law": string,
  "customer": string,
  "vendor": string,
  "bank_account": string,
  "required_attachments": string[]
}
Rules:
- Map meaning onto those fields. Canonicalize numbers ("$50,000.00" → 50000, "USD 500,000" → 500000).
- Do not decide whether the document is safe.
- Do not say the terms match. Do not open or close any gate.
- If a field is not present, use null (or [] for attachments).
"""


def extract_llm_json(manifest: IntentManifest, extracted: ExtractedTerms) -> tuple[dict[str, Any] | None, bool]:
    if not os.environ.get("OPENAI_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
        return None, False
    payload = json.dumps(
        {
            "instruction": "Extract canonical terms from the Foxit/OCR text. Do not compare. Do not approve.",
            "intent_manifest_schema_example": {
                "contract_value_amount": manifest["commercial_terms"]["contract_value"]["amount"],
                "fields": [
                    "contract_value_amount",
                    "contract_value_currency",
                    "term_months",
                    "payment_terms_days",
                    "termination_notice_days",
                    "auto_renewal",
                    "personal_guarantee",
                    "exclusivity",
                    "governing_law",
                    "customer",
                    "vendor",
                    "bank_account",
                    "required_attachments",
                ],
            },
            "foxit_extracted_text": extracted["raw_text"][:12000],
        },
        indent=2,
    )
    try:
        raw = _openai(payload) if os.environ.get("OPENAI_API_KEY") else _anthropic(payload)
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and "findings" in parsed and "contract_value_amount" not in parsed:
            parsed = parsed.get("extracted") or parsed.get("terms") or parsed
        return parsed if isinstance(parsed, dict) else None, True
    except Exception:
        return None, True


def _openai(user: str) -> str:
    res = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "Content-Type": "application/json"},
        json={
            "model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": user}],
        },
        timeout=60,
    )
    res.raise_for_status()
    return res.json()["choices"][0]["message"]["content"]


def _anthropic(user: str) -> str:
    res = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""),
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            "max_tokens": 1200,
            "temperature": 0,
            "system": PROMPT,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=60,
    )
    res.raise_for_status()
    text = "".join(part.get("text", "") for part in res.json().get("content", []))
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise RuntimeError("No JSON in Anthropic response")
    return text[start : end + 1]
