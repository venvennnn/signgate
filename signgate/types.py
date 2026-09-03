from __future__ import annotations

from typing import Any, Literal, TypedDict, NotRequired

Severity = Literal["cosmetic", "clarifying", "material", "critical", "uncertain"]
VerificationLayer = Literal["exact", "structural", "semantic"]
DocumentStatus = Literal[
    "draft_intent",
    "awaiting_approval",
    "approved",
    "generated",
    "verified_open",
    "verified_blocked",
    "sent_for_signature",
]


class Money(TypedDict):
    amount: int
    currency: str


class IntentManifest(TypedDict):
    document_type: str
    title: str
    parties: dict[str, str]
    commercial_terms: dict[str, Any]
    legal_terms: dict[str, Any]
    required_attachments: list[str]
    must_not_include: list[str]
    bank_details: dict[str, str | None]
    signer: dict[str, str]


class ExtractedTerms(TypedDict):
    parties: dict[str, str | None]
    commercial_terms: dict[str, Any]
    legal_terms: dict[str, Any]
    attachments_found: list[str]
    bank_details: dict[str, str | None]
    signer_names: list[str]
    page_count: int
    field_pages: dict[str, int | None]
    excerpts: dict[str, str]
    raw_text: str


class Discrepancy(TypedDict):
    id: str
    severity: Severity
    layer: VerificationLayer
    field: str
    title: str
    approved_value: str
    found_value: str
    page: int | None
    excerpt: str | None
    rationale: str
    confidence: float


class TwoPassResult(TypedDict):
    parser_json: dict[str, Any]
    llm_json: dict[str, Any] | None
    llm_raw: dict[str, Any] | None
    llm_used: bool
    llm_may_not_open_gate: bool
    deterministic_winner: Literal["python"]
    parser_mismatches: list[dict[str, Any]]
    llm_mismatches: list[dict[str, Any]]
    llm_parser_conflicts: list[dict[str, Any]]
    approved_json: dict[str, Any]


class PipelineStep(TypedDict):
    tool: str
    foxit_operation: str | None
    provider: Literal["foxit", "local"]
    status: Literal["ok", "fallback", "failed", "skipped"]
    detail: str
    created_at: NotRequired[str]


class GateDecision(TypedDict):
    status: Literal["open", "blocked"]
    semantic_checksum: str
    extracted_checksum: str
    critical_count: int
    material_count: int
    clarifying_count: int
    cosmetic_count: int
    uncertain_count: int
    verified_term_count: int
    missing_attachments: list[str]
    discrepancies: list[Discrepancy]
    llm_used: bool
    llm_may_not_open_gate: bool
    two_pass: NotRequired[TwoPassResult]
    cover_sheet_attached: NotRequired[bool]
    extraction_provider: NotRequired[str]
