import { describe, expect, it } from "vitest";
import { extractIntent } from "./intent";

describe("extractIntent", () => {
  it("captures the killer-demo vendor request", () => {
    const manifest = extractIntent(
      "Create a one-year data-services agreement for $50,000, with 30-day termination and no automatic renewal.",
    );
    expect(manifest.document_type).toBe("vendor_agreement");
    expect(manifest.commercial_terms.contract_value).toEqual({ amount: 50000, currency: "USD" });
    expect(manifest.commercial_terms.term_months).toBe(12);
    expect(manifest.legal_terms.termination_notice_days).toBe(30);
    expect(manifest.legal_terms.auto_renewal).toBe(false);
    expect(manifest.legal_terms.governing_law).toBe("Singapore");
    expect(manifest.required_attachments).toContain("Statement of Work");
    expect(manifest.must_not_include).toEqual(
      expect.arrayContaining(["Automatic renewal", "Personal liability", "Exclusivity"]),
    );
  });

  it("picks up named parties, law, and auto-renewal", () => {
    const manifest = extractIntent(
      "12-month vendor agreement with Helios Cloud for Northstar Analytics as the customer, SGD 120,000, governed by the laws of England, automatic renewal, 15-day termination.",
    );
    expect(manifest.parties.vendor).toMatch(/Helios Cloud/);
    expect(manifest.commercial_terms.contract_value).toEqual({ amount: 120000, currency: "SGD" });
    expect(manifest.legal_terms.auto_renewal).toBe(true);
    expect(manifest.legal_terms.termination_notice_days).toBe(15);
    expect(manifest.legal_terms.governing_law).toMatch(/England/i);
  });
});
