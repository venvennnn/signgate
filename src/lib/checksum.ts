import { createHash } from "node:crypto";
import type { ExtractedTerms, IntentManifest, SemanticChecksum } from "./types";

function moneyLabel(amount: number, currency: string) {
  return `${currency} ${amount.toLocaleString("en-US")}`;
}

export function checksumFromManifest(manifest: IntentManifest): SemanticChecksum {
  return {
    contract_value: moneyLabel(
      manifest.commercial_terms.contract_value.amount,
      manifest.commercial_terms.contract_value.currency,
    ),
    termination_notice: `${manifest.legal_terms.termination_notice_days} days`,
    auto_renewal: manifest.legal_terms.auto_renewal,
    personal_guarantee: manifest.legal_terms.personal_guarantee,
    exclusivity: manifest.legal_terms.exclusivity,
    governing_law: manifest.legal_terms.governing_law,
    term_months: manifest.commercial_terms.term_months,
    payment_terms_days: manifest.commercial_terms.payment_terms_days,
    customer: manifest.parties.customer,
    vendor: manifest.parties.vendor,
    required_attachments: [...manifest.required_attachments].sort(),
    bank_account: manifest.bank_details.account_number,
  };
}

export function checksumFromExtracted(extracted: ExtractedTerms): SemanticChecksum {
  const value = extracted.commercial_terms.contract_value;
  return {
    contract_value: value ? moneyLabel(value.amount, value.currency) : "unextracted",
    termination_notice:
      extracted.legal_terms.termination_notice_days != null
        ? `${extracted.legal_terms.termination_notice_days} days`
        : "unextracted",
    auto_renewal: extracted.legal_terms.auto_renewal ?? false,
    personal_guarantee: extracted.legal_terms.personal_guarantee ?? false,
    exclusivity: extracted.legal_terms.exclusivity ?? false,
    governing_law: extracted.legal_terms.governing_law ?? "unextracted",
    term_months: extracted.commercial_terms.term_months ?? -1,
    payment_terms_days: extracted.commercial_terms.payment_terms_days ?? -1,
    customer: extracted.parties.customer ?? "unextracted",
    vendor: extracted.parties.vendor ?? "unextracted",
    required_attachments: [...extracted.attachments_found].sort(),
    bank_account: extracted.bank_details.account_number,
  };
}

export function fingerprint(checksum: SemanticChecksum): string {
  const canonical = JSON.stringify(checksum, Object.keys(checksum).sort());
  return createHash("sha256").update(canonical).digest("hex");
}

export function shortFingerprint(checksum: SemanticChecksum): string {
  return fingerprint(checksum).slice(0, 16);
}
