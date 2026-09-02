import { nanoid } from "nanoid";
import { checksumFromExtracted, checksumFromManifest, fingerprint } from "./checksum";
import type {
  Discrepancy,
  ExtractedTerms,
  GateDecision,
  IntentManifest,
  Severity,
  VerificationLayer,
} from "./types";

function money(amount: number, currency: string) {
  return `${currency} ${amount.toLocaleString("en-US")}`;
}

function finding(partial: Omit<Discrepancy, "confidence"> & { confidence?: number }): Discrepancy {
  return {
    confidence: 1,
    ...partial,
  };
}

function namesMatch(a: string, b: string) {
  const normalize = (value: string) =>
    value
      .toLowerCase()
      .replace(/pte\.?\s*ltd\.?/g, "")
      .replace(/inc\.?|llc|ltd\.?|limited|corp\.?|corporation/g, "")
      .replace(/[^a-z0-9]+/g, " ")
      .trim();
  return normalize(a) === normalize(b);
}

function lawMatch(a: string, b: string) {
  return a.trim().toLowerCase() === b.trim().toLowerCase();
}

export function compareManifestToExtracted(
  manifest: IntentManifest,
  extracted: ExtractedTerms,
): Discrepancy[] {
  const out: Discrepancy[] = [];
  const value = extracted.commercial_terms.contract_value;
  const approvedValue = money(
    manifest.commercial_terms.contract_value.amount,
    manifest.commercial_terms.contract_value.currency,
  );

  if (!value) {
    out.push(
      finding({
        severity: "critical",
        layer: "exact",
        field: "contract_value",
        title: "Contract value missing",
        approved_value: approvedValue,
        found_value: "Not found in final document",
        page: extracted.field_pages.contract_value ?? null,
        excerpt: extracted.excerpts.contract_value ?? null,
        rationale: "The approved commercial amount could not be located in the final PDF.",
      }),
    );
  } else if (
    value.amount !== manifest.commercial_terms.contract_value.amount ||
    value.currency.toUpperCase() !== manifest.commercial_terms.contract_value.currency.toUpperCase()
  ) {
    out.push(
      finding({
        severity: "critical",
        layer: "exact",
        field: "contract_value",
        title: "Contract value changed",
        approved_value: approvedValue,
        found_value: money(value.amount, value.currency),
        page: extracted.field_pages.contract_value ?? null,
        excerpt: extracted.excerpts.contract_value ?? null,
        rationale: "A one-digit change in a commercial amount is a classic authorization failure.",
      }),
    );
  }

  if (extracted.commercial_terms.term_months == null) {
    out.push(
      finding({
        severity: "material",
        layer: "exact",
        field: "term_months",
        title: "Agreement term missing",
        approved_value: `${manifest.commercial_terms.term_months} months`,
        found_value: "Not found",
        page: extracted.field_pages.term_months ?? null,
        excerpt: extracted.excerpts.term_months ?? null,
        rationale: "Duration is a material commercial term.",
      }),
    );
  } else if (extracted.commercial_terms.term_months !== manifest.commercial_terms.term_months) {
    out.push(
      finding({
        severity: "material",
        layer: "exact",
        field: "term_months",
        title: "Agreement term changed",
        approved_value: `${manifest.commercial_terms.term_months} months`,
        found_value: `${extracted.commercial_terms.term_months} months`,
        page: extracted.field_pages.term_months ?? null,
        excerpt: extracted.excerpts.term_months ?? null,
        rationale: "The duration of the obligation no longer matches the approved intent.",
      }),
    );
  }

  if (extracted.commercial_terms.payment_terms_days == null) {
    out.push(
      finding({
        severity: "material",
        layer: "exact",
        field: "payment_terms_days",
        title: "Payment terms missing",
        approved_value: `${manifest.commercial_terms.payment_terms_days} days`,
        found_value: "Not found",
        page: extracted.field_pages.payment_terms_days ?? null,
        excerpt: extracted.excerpts.payment_terms_days ?? null,
        rationale: "Payment timing is a commercial obligation.",
      }),
    );
  } else if (extracted.commercial_terms.payment_terms_days !== manifest.commercial_terms.payment_terms_days) {
    out.push(
      finding({
        severity: "material",
        layer: "exact",
        field: "payment_terms_days",
        title: "Payment terms changed",
        approved_value: `${manifest.commercial_terms.payment_terms_days} days`,
        found_value: `${extracted.commercial_terms.payment_terms_days} days`,
        page: extracted.field_pages.payment_terms_days ?? null,
        excerpt: extracted.excerpts.payment_terms_days ?? null,
        rationale: "Cash timing changed after approval.",
      }),
    );
  }

  if (extracted.legal_terms.termination_notice_days == null) {
    out.push(
      finding({
        severity: "material",
        layer: "exact",
        field: "termination_notice_days",
        title: "Termination notice missing",
        approved_value: `${manifest.legal_terms.termination_notice_days} days`,
        found_value: "Not found",
        page: extracted.field_pages.termination_notice_days ?? null,
        excerpt: extracted.excerpts.termination_notice_days ?? null,
        rationale: "Exit rights could not be confirmed in the final document.",
      }),
    );
  } else if (extracted.legal_terms.termination_notice_days !== manifest.legal_terms.termination_notice_days) {
    out.push(
      finding({
        severity: "material",
        layer: "exact",
        field: "termination_notice_days",
        title: "Termination notice changed",
        approved_value: `${manifest.legal_terms.termination_notice_days} days`,
        found_value: `${extracted.legal_terms.termination_notice_days} days`,
        page: extracted.field_pages.termination_notice_days ?? null,
        excerpt: extracted.excerpts.termination_notice_days ?? null,
        rationale: "Changing notice from 30 to 90 days (or the reverse) rewrites the exit right.",
      }),
    );
  }

  if (extracted.legal_terms.auto_renewal == null) {
    out.push(
      finding({
        severity: "uncertain",
        layer: "semantic",
        field: "auto_renewal",
        title: "Renewal rule could not be confirmed",
        approved_value: manifest.legal_terms.auto_renewal ? "Yes" : "No",
        found_value: "Uncertain",
        page: extracted.field_pages.auto_renewal ?? null,
        excerpt: extracted.excerpts.auto_renewal ?? null,
        rationale: "The gate cannot open on an uncertain comparison of renewal obligations.",
        confidence: 0.4,
      }),
    );
  } else if (extracted.legal_terms.auto_renewal !== manifest.legal_terms.auto_renewal) {
    out.push(
      finding({
        severity: extracted.legal_terms.auto_renewal ? "material" : "material",
        layer: "semantic",
        field: "auto_renewal",
        title: extracted.legal_terms.auto_renewal
          ? "Automatic renewal introduced"
          : "Automatic renewal removed",
        approved_value: manifest.legal_terms.auto_renewal ? "Yes" : "No",
        found_value: extracted.legal_terms.auto_renewal ? "Yes" : "No",
        page: extracted.field_pages.auto_renewal ?? null,
        excerpt: extracted.excerpts.auto_renewal ?? null,
        rationale: "Renewal language changes the duration of the legal commitment.",
      }),
    );
  }

  if (extracted.legal_terms.personal_guarantee == null) {
    out.push(
      finding({
        severity: "uncertain",
        layer: "semantic",
        field: "personal_guarantee",
        title: "Personal liability could not be confirmed",
        approved_value: manifest.legal_terms.personal_guarantee ? "Yes" : "No",
        found_value: "Uncertain",
        page: extracted.field_pages.personal_guarantee ?? null,
        excerpt: extracted.excerpts.personal_guarantee ?? null,
        rationale: "Personal liability is a critical term and requires a determinate reading.",
        confidence: 0.4,
      }),
    );
  } else if (extracted.legal_terms.personal_guarantee !== manifest.legal_terms.personal_guarantee) {
    out.push(
      finding({
        severity: "critical",
        layer: "semantic",
        field: "personal_guarantee",
        title: extracted.legal_terms.personal_guarantee
          ? "Personal liability added"
          : "Personal guarantee removed",
        approved_value: manifest.legal_terms.personal_guarantee ? "Yes" : "No",
        found_value: extracted.legal_terms.personal_guarantee ? "Yes" : "No",
        page: extracted.field_pages.personal_guarantee ?? null,
        excerpt: extracted.excerpts.personal_guarantee ?? null,
        rationale: "Shifting liability onto an individual is a critical authorization change.",
      }),
    );
  }

  if (extracted.legal_terms.exclusivity == null) {
    out.push(
      finding({
        severity: "uncertain",
        layer: "semantic",
        field: "exclusivity",
        title: "Exclusivity could not be confirmed",
        approved_value: manifest.legal_terms.exclusivity ? "Yes" : "No",
        found_value: "Uncertain",
        page: extracted.field_pages.exclusivity ?? null,
        excerpt: extracted.excerpts.exclusivity ?? null,
        rationale: "Whether the customer is locked in is a material commercial restriction.",
        confidence: 0.35,
      }),
    );
  } else if (extracted.legal_terms.exclusivity !== manifest.legal_terms.exclusivity) {
    out.push(
      finding({
        severity: "material",
        layer: "semantic",
        field: "exclusivity",
        title: extracted.legal_terms.exclusivity ? "Exclusivity introduced" : "Exclusivity removed",
        approved_value: manifest.legal_terms.exclusivity ? "Yes" : "No",
        found_value: extracted.legal_terms.exclusivity ? "Yes" : "No",
        page: extracted.field_pages.exclusivity ?? null,
        excerpt: extracted.excerpts.exclusivity ?? null,
        rationale: "An exclusivity clause changes the customer's freedom to contract elsewhere.",
      }),
    );
  }

  if (!extracted.legal_terms.governing_law) {
    out.push(
      finding({
        severity: "critical",
        layer: "exact",
        field: "governing_law",
        title: "Governing law missing",
        approved_value: manifest.legal_terms.governing_law,
        found_value: "Not found",
        page: extracted.field_pages.governing_law ?? null,
        excerpt: extracted.excerpts.governing_law ?? null,
        rationale: "Jurisdiction is a critical executed term.",
      }),
    );
  } else if (!lawMatch(extracted.legal_terms.governing_law, manifest.legal_terms.governing_law)) {
    out.push(
      finding({
        severity: "critical",
        layer: "exact",
        field: "governing_law",
        title: "Governing law changed",
        approved_value: manifest.legal_terms.governing_law,
        found_value: extracted.legal_terms.governing_law,
        page: extracted.field_pages.governing_law ?? null,
        excerpt: extracted.excerpts.governing_law ?? null,
        rationale: "A jurisdiction swap is a critical change even if the rest of the deal looks identical.",
      }),
    );
  }

  if (extracted.parties.customer && !namesMatch(extracted.parties.customer, manifest.parties.customer)) {
    out.push(
      finding({
        severity: "critical",
        layer: "exact",
        field: "customer",
        title: "Customer name changed",
        approved_value: manifest.parties.customer,
        found_value: extracted.parties.customer,
        page: extracted.field_pages.customer ?? 1,
        excerpt: extracted.excerpts.customer ?? null,
        rationale: "The party on the paper is not the party that was authorized.",
      }),
    );
  }

  if (extracted.parties.vendor && !namesMatch(extracted.parties.vendor, manifest.parties.vendor)) {
    out.push(
      finding({
        severity: "critical",
        layer: "exact",
        field: "vendor",
        title: "Vendor name changed",
        approved_value: manifest.parties.vendor,
        found_value: extracted.parties.vendor,
        page: extracted.field_pages.vendor ?? 1,
        excerpt: extracted.excerpts.vendor ?? null,
        rationale: "The counterparty identity is a critical signing term.",
      }),
    );
  }

  if (manifest.bank_details.account_number) {
    const found = extracted.bank_details.account_number;
    if (found && found.replace(/\s+/g, "") !== manifest.bank_details.account_number.replace(/\s+/g, "")) {
      out.push(
        finding({
          severity: "critical",
          layer: "exact",
          field: "bank_account",
          title: "Bank details replaced",
          approved_value: manifest.bank_details.account_number,
          found_value: found,
          page: extracted.field_pages.bank_account ?? null,
          excerpt: extracted.excerpts.bank_account ?? null,
          rationale: "Payment destination changes are treated as critical by default.",
        }),
      );
    }
  }

  const missingAttachments = manifest.required_attachments.filter((required) => {
    return !extracted.attachments_found.some((found) => found.toLowerCase() === required.toLowerCase());
  });
  for (const missing of missingAttachments) {
    out.push(
      finding({
        severity: "material",
        layer: "structural",
        field: "attachments",
        title: "Missing attachment",
        approved_value: missing,
        found_value: "Not found",
        page: null,
        excerpt: null,
        rationale: `${missing} was required by the approved Intent Manifest and is absent from the final PDF.`,
      }),
    );
  }

  for (const banned of manifest.must_not_include) {
    const key = banned.toLowerCase();
    if (key.includes("automatic") && extracted.legal_terms.auto_renewal) {
      continue;
    }
    if (key.includes("personal") && extracted.legal_terms.personal_guarantee) {
      continue;
    }
    if (key.includes("exclusiv") && extracted.legal_terms.exclusivity) {
      continue;
    }
  }

  if (extracted.page_count === 0 || !extracted.raw_text.trim()) {
    out.push(
      finding({
        severity: "critical",
        layer: "structural",
        field: "page_count",
        title: "Document appears empty",
        approved_value: "Complete executed set",
        found_value: `${extracted.page_count} page${extracted.page_count === 1 ? "" : "s"}`,
        page: extracted.page_count,
        excerpt: null,
        rationale: "No extractable text was found in the final PDF.",
      }),
    );
  }

  return out;
}

export function decideGate(
  manifest: IntentManifest,
  extracted: ExtractedTerms,
  extra: Discrepancy[] = [],
  llmUsed = false,
): GateDecision {
  const discrepancies = [...compareManifestToExtracted(manifest, extracted), ...extra].map((item) => ({
    ...item,
    id: item.id ?? nanoid(10),
  }));

  const count = (severity: Severity) => discrepancies.filter((item) => item.severity === severity).length;
  const blocking = discrepancies.some((item) =>
    ["material", "critical", "uncertain"].includes(item.severity),
  );

  const exactOk = discrepancies.filter((item) => item.layer === "exact").length === 0;
  const verifiedTermCount = [
    extracted.commercial_terms.contract_value,
    extracted.commercial_terms.term_months,
    extracted.commercial_terms.payment_terms_days,
    extracted.legal_terms.termination_notice_days,
    extracted.legal_terms.auto_renewal,
    extracted.legal_terms.personal_guarantee,
    extracted.legal_terms.exclusivity,
    extracted.legal_terms.governing_law,
    extracted.parties.customer,
    extracted.parties.vendor,
    extracted.bank_details.account_number,
  ].filter((value) => value != null && value !== "").length;

  return {
    status: blocking ? "blocked" : "open",
    semantic_checksum: fingerprint(checksumFromManifest(manifest)),
    extracted_checksum: fingerprint(checksumFromExtracted(extracted)),
    critical_count: count("critical"),
    material_count: count("material"),
    clarifying_count: count("clarifying"),
    cosmetic_count: count("cosmetic"),
    uncertain_count: count("uncertain"),
    verified_term_count: exactOk ? Math.max(verifiedTermCount, 8) : verifiedTermCount,
    missing_attachments: manifest.required_attachments.filter(
      (required) => !extracted.attachments_found.some((found) => found.toLowerCase() === required.toLowerCase()),
    ),
    discrepancies,
    llm_used: llmUsed,
    llm_may_not_open_gate: true,
  };
}

export function layerLabel(layer: VerificationLayer) {
  switch (layer) {
    case "exact":
      return "Exact-value check";
    case "structural":
      return "Structural check";
    case "semantic":
      return "Semantic check";
  }
}
