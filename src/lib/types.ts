export const DOCUMENT_TYPE = "vendor_agreement" as const;

export type Severity = "cosmetic" | "clarifying" | "material" | "critical" | "uncertain";
export type VerificationLayer = "exact" | "structural" | "semantic";
export type GateStatus = "closed" | "open" | "blocked";
export type DocumentStatus =
  | "draft_intent"
  | "awaiting_approval"
  | "approved"
  | "generated"
  | "verified_open"
  | "verified_blocked"
  | "sent_for_signature";

export type Money = {
  amount: number;
  currency: string;
};

export type IntentManifest = {
  document_type: typeof DOCUMENT_TYPE;
  title: string;
  parties: {
    customer: string;
    vendor: string;
  };
  commercial_terms: {
    contract_value: Money;
    term_months: number;
    payment_terms_days: number;
    services_description: string;
  };
  legal_terms: {
    termination_notice_days: number;
    auto_renewal: boolean;
    governing_law: string;
    personal_guarantee: boolean;
    exclusivity: boolean;
  };
  required_attachments: string[];
  must_not_include: string[];
  bank_details: {
    account_name: string | null;
    account_number: string | null;
    bank_name: string | null;
  };
  signer: {
    name: string;
    email: string;
    title: string;
  };
};

export type ExtractedTerms = {
  parties: {
    customer: string | null;
    vendor: string | null;
  };
  commercial_terms: {
    contract_value: Money | null;
    term_months: number | null;
    payment_terms_days: number | null;
  };
  legal_terms: {
    termination_notice_days: number | null;
    auto_renewal: boolean | null;
    governing_law: string | null;
    personal_guarantee: boolean | null;
    exclusivity: boolean | null;
  };
  attachments_found: string[];
  bank_details: {
    account_name: string | null;
    account_number: string | null;
    bank_name: string | null;
  };
  signer_names: string[];
  page_count: number;
  field_pages: Record<string, number | null>;
  excerpts: Record<string, string>;
  raw_text: string;
};

export type Discrepancy = {
  id?: string;
  severity: Severity;
  layer: VerificationLayer;
  field: string;
  title: string;
  approved_value: string;
  found_value: string;
  page: number | null;
  excerpt: string | null;
  rationale: string;
  confidence: number;
};

export type GateDecision = {
  status: "open" | "blocked";
  semantic_checksum: string;
  extracted_checksum: string;
  critical_count: number;
  material_count: number;
  clarifying_count: number;
  cosmetic_count: number;
  uncertain_count: number;
  verified_term_count: number;
  missing_attachments: string[];
  discrepancies: Discrepancy[];
  llm_used: boolean;
  llm_may_not_open_gate: true;
};

export type SemanticChecksum = {
  contract_value: string;
  termination_notice: string;
  auto_renewal: boolean;
  personal_guarantee: boolean;
  exclusivity: boolean;
  governing_law: string;
  term_months: number;
  payment_terms_days: number;
  customer: string;
  vendor: string;
  required_attachments: string[];
  bank_account: string | null;
};

export type AuditEvent = {
  id: string;
  document_id: string;
  actor: string;
  timestamp: string;
  document_hash: string | null;
  manifest_version: number | null;
  action: string;
  previous_state: string | null;
  new_state: string | null;
  reason: string | null;
  metadata: Record<string, unknown> | null;
};

export type DocumentRecord = {
  id: string;
  title: string;
  document_type: string;
  status: DocumentStatus;
  prompt: string;
  actor: string;
  created_at: string;
  updated_at: string;
};

export type ManifestRecord = {
  id: string;
  document_id: string;
  version: number;
  payload: IntentManifest;
  status: "draft" | "approved" | "superseded";
  created_at: string;
};

export type VersionRecord = {
  id: string;
  document_id: string;
  version: number;
  source: "generated" | "uploaded" | "restored" | "adversarial";
  file_path: string;
  sha256: string;
  page_count: number;
  created_at: string;
  is_current: boolean;
  notes: string | null;
};

export type SessionSnapshot = {
  document: DocumentRecord;
  manifest: ManifestRecord | null;
  approved_manifest: ManifestRecord | null;
  current_version: VersionRecord | null;
  versions: VersionRecord[];
  extracted: ExtractedTerms | null;
  decision: GateDecision | null;
  signature_request: {
    id: string;
    provider: string;
    provider_ref: string | null;
    signer_email: string;
    status: string;
    created_at: string;
  } | null;
  audit: AuditEvent[];
  foxit_configured: boolean;
};
