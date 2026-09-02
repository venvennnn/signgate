import { describe, expect, it } from "vitest";
import { extractTermsFromPages } from "./extract";
import { adversarialManifest, defaultManifest } from "./intent";
import { generateAgreementPdf } from "./pdf";
import { extractPdfTerms } from "./pdf-extract";
import { decideGate } from "./verify";

const approvedText = [
  `DATA SERVICES AGREEMENT
Customer: Northstar Analytics
Vendor: Atlas Systems
1.1 Contract Value. The total contract value is USD 50,000.
1.2 Term. This Agreement shall remain in force for 12 months.
1.3 Payment. Invoices are payable within 30 days.
2.1 Either party may terminate this Agreement by providing 30 days written notice.
2.2 This Agreement does not automatically renew.
3.1 Governing Law. This Agreement is governed by the laws of Singapore.
3.2 Liability. Neither party provides a personal guarantee. No personal liability is assumed by any director.
3.3 Exclusivity. This Agreement does not grant exclusivity.
Account name: Atlas Systems Pte. Ltd.
Bank: DBS Bank
Account number: 001-4729183
Schedule A — Statement of Work
This Statement of Work is attached to and forms part of the Agreement.`,
];

describe("verification engine", () => {
  it("opens the gate when the document matches the approved manifest", () => {
    const manifest = defaultManifest();
    const extracted = extractTermsFromPages(approvedText);
    const decision = decideGate(manifest, extracted);
    expect(decision.status).toBe("open");
    expect(decision.critical_count).toBe(0);
    expect(decision.material_count).toBe(0);
    expect(decision.missing_attachments).toEqual([]);
    expect(decision.llm_may_not_open_gate).toBe(true);
  });

  it("blocks the killer-demo adversarial edit", () => {
    const manifest = defaultManifest();
    const extracted = extractTermsFromPages([
      `DATA SERVICES AGREEMENT
Customer: Northstar Analytics
Vendor: Atlas Systems
Contract Value. The total contract value is USD 500,000.
Term. This Agreement shall remain in force for 12 months.
Payment. Invoices are payable within 30 days.
Either party may terminate this Agreement by providing 90 days written notice.
This Agreement automatically renews for successive 12-month periods unless either party provides 90 days written notice.
Governing Law. This Agreement is governed by the laws of Singapore.
Neither party provides a personal guarantee.
This Agreement does not grant exclusivity.
Account number: 001-4729183`,
    ]);
    const decision = decideGate(manifest, extracted);
    expect(decision.status).toBe("blocked");
    const fields = decision.discrepancies.map((item) => item.field);
    expect(fields).toContain("contract_value");
    expect(fields).toContain("termination_notice_days");
    expect(fields).toContain("auto_renewal");
    expect(fields).toContain("attachments");
    const value = decision.discrepancies.find((item) => item.field === "contract_value")!;
    expect(value.severity).toBe("critical");
    expect(value.approved_value).toContain("50,000");
    expect(value.found_value).toContain("500,000");
  });

  it("treats governing-law and bank-detail swaps as critical", () => {
    const manifest = defaultManifest();
    const extracted = extractTermsFromPages([
      approvedText[0]
        .replace("Singapore", "Delaware")
        .replace("001-4729183", "999-0001112"),
    ]);
    const decision = decideGate(manifest, extracted);
    expect(decision.status).toBe("blocked");
    expect(decision.discrepancies.some((item) => item.field === "governing_law" && item.severity === "critical")).toBe(
      true,
    );
    expect(decision.discrepancies.some((item) => item.field === "bank_account" && item.severity === "critical")).toBe(
      true,
    );
  });

  it("blocks when personal liability is inserted", () => {
    const manifest = defaultManifest();
    const extracted = extractTermsFromPages([
      approvedText[0].replace(
        "Neither party provides a personal guarantee. No personal liability is assumed by any director.",
        "The undersigned individual personally guarantees the Customer's obligations under this Agreement.",
      ),
    ]);
    const decision = decideGate(manifest, extracted);
    expect(decision.discrepancies.some((item) => item.field === "personal_guarantee")).toBe(true);
    expect(decision.status).toBe("blocked");
  });
});

describe("pdf round-trip", () => {
  it("generates an approved PDF that verifies open, and an adversarial PDF that blocks", async () => {
    const approved = defaultManifest();
    const good = await generateAgreementPdf(approved);
    const goodTerms = await extractPdfTerms(good.buffer);
    const open = decideGate(approved, goodTerms);
    expect(open.status).toBe("open");
    expect(goodTerms.attachments_found).toContain("Statement of Work");

    const bad = await generateAgreementPdf(adversarialManifest(approved), { adversarial: true });
    const badTerms = await extractPdfTerms(bad.buffer);
    const blocked = decideGate(approved, badTerms);
    expect(blocked.status).toBe("blocked");
    expect(badTerms.commercial_terms.contract_value?.amount).toBe(500000);
    expect(badTerms.legal_terms.auto_renewal).toBe(true);
    expect(badTerms.attachments_found).not.toContain("Statement of Work");
  });
});
