from __future__ import annotations

import json
import os
from typing import Any

import requests

from .types import Discrepancy, ExtractedTerms, IntentManifest

PROMPT = """You are a legal-meaning reviewer for SignGate.
The human already approved an Intent Manifest. Compare it to terms extracted from a final PDF.
Propose discrepancies only when the legal meaning changed.
Do not declare the contract safe. Do not open or close the signature gate.
Return JSON: { "findings": [{ "field": string, "title": string, "severity": "clarifying"|"material"|"critical"|"uncertain", "approved_value": string, "found_value": string, "rationale": string, "confidence": number }] }
If you are not sure, emit severity "uncertain". Empty findings is allowed."""


def propose_semantic_findings(manifest: IntentManifest, extracted: ExtractedTerms) -> tuple[list[Discrepancy], bool]:
    if not os.environ.get("OPENAI_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
        return [], False
    payload = json.dumps(
        {
            "approved_manifest": manifest,
            "extracted_terms": {
                "parties": extracted["parties"],
                "commercial_terms": extracted["commercial_terms"],
                "legal_terms": extracted["legal_terms"],
                "attachments_found": extracted["attachments_found"],
                "excerpts": extracted["excerpts"],
                "sample_text": extracted["raw_text"][:8000],
            },
        },
        indent=2,
    )
    try:
        raw = _openai(payload) if os.environ.get("OPENAI_API_KEY") else _anthropic(payload)
        parsed = json.loads(raw)
        findings: list[Discrepancy] = []
        for item in parsed.get("findings") or []:
            findings.append(
                {
                    "id": item.get("field", "semantic"),
                    "severity": item.get("severity", "uncertain"),
                    "layer": "semantic",
                    "field": item.get("field", "semantic_review"),
                    "title": item.get("title", "Semantic finding"),
                    "approved_value": item.get("approved_value", ""),
                    "found_value": item.get("found_value", ""),
                    "page": extracted["field_pages"].get(item.get("field", "")),
                    "excerpt": extracted["excerpts"].get(item.get("field", "")),
                    "rationale": f"{item.get('rationale', '')} (LLM proposal — not independently authoritative.)",
                    "confidence": float(item.get("confidence", 0.6)),
                }
            )
        return findings, True
    except Exception:
        return [
            {
                "id": "semantic_review",
                "severity": "uncertain",
                "layer": "semantic",
                "field": "semantic_review",
                "title": "Semantic reviewer failed",
                "approved_value": "Deterministic checks still apply",
                "found_value": "LLM proposal unavailable",
                "page": None,
                "excerpt": None,
                "rationale": "The language model could not complete a semantic review. The gate stays conservative.",
                "confidence": 0.2,
            }
        ], True


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
