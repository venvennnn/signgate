import PDFDocument from "pdfkit";
import type { IntentManifest } from "./types";

function money(manifest: IntentManifest) {
  const { amount, currency } = manifest.commercial_terms.contract_value;
  return `${currency} ${amount.toLocaleString("en-US")}`;
}

function collectPdf(draw: (doc: PDFKit.PDFDocument) => void): Promise<Buffer> {
  const doc = new PDFDocument({ size: "LETTER", margin: 64, bufferPages: true });
  const chunks: Buffer[] = [];
  doc.on("data", (chunk) => chunks.push(chunk as Buffer));
  const done = new Promise<Buffer>((resolve, reject) => {
    doc.on("end", () => resolve(Buffer.concat(chunks)));
    doc.on("error", reject);
  });
  draw(doc);
  doc.end();
  return done;
}

function header(doc: PDFKit.PDFDocument, title: string, subtitle: string) {
  doc.fillColor("#1B1A16").font("Times-Bold").fontSize(18).text("SIGNGATE", { align: "left" });
  doc.fillColor("#8A6A2F").font("Times-Italic").fontSize(9).text("Authorization integrity copy", { align: "left" });
  doc.moveDown(0.4);
  doc.fillColor("#1B1A16").font("Times-Bold").fontSize(16).text(title, { align: "center" });
  doc.font("Times-Roman").fontSize(10).fillColor("#444").text(subtitle, { align: "center" });
  doc.moveDown(0.8);
  doc.strokeColor("#C6A15B").lineWidth(1).moveTo(64, doc.y).lineTo(548, doc.y).stroke();
  doc.moveDown(0.8);
}

function footer(doc: PDFKit.PDFDocument, page: number, total: number) {
  doc.font("Times-Italic").fontSize(8).fillColor("#777").text(
    `Page ${page} of ${total}  ·  This PDF is not legally binding until a human signs after SignGate verification.`,
    64,
    740,
    { width: 484, align: "center" },
  );
}

export function agreementHtml(manifest: IntentManifest, opts?: { adversarial?: boolean }): string {
  const value = money(manifest);
  const sow = manifest.required_attachments.includes("Statement of Work");
  const renew = manifest.legal_terms.auto_renewal
    ? `This Agreement <strong>automatically renews</strong> for successive ${manifest.commercial_terms.term_months}-month periods unless either party provides ${manifest.legal_terms.termination_notice_days} days' written notice.`
    : `This Agreement <strong>does not automatically renew</strong>. Any extension requires a new written instrument signed by both parties.`;
  const guarantee = manifest.legal_terms.personal_guarantee
    ? `The undersigned individual <strong>personally guarantees</strong> the Customer's obligations under this Agreement.`
    : `Neither party provides a personal guarantee. No personal liability is assumed by any director, officer, or employee.`;
  const exclusive = manifest.legal_terms.exclusivity
    ? `Customer hereby appoints Vendor as its exclusive provider of the Services.`
    : `This Agreement does not grant exclusivity. Customer may obtain similar services from other vendors.`;

  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>${manifest.title}</title>
  <style>
    body { font-family: "Times New Roman", serif; color: #1b1a16; margin: 48px; }
    h1 { text-align: center; letter-spacing: 0.04em; }
    h2 { border-bottom: 1px solid #c6a15b; padding-bottom: 4px; }
    .meta { color: #555; text-align: center; }
    table { width: 100%; border-collapse: collapse; margin: 12px 0 20px; }
    td { border: 1px solid #ddd; padding: 8px; vertical-align: top; }
    .label { width: 34%; background: #f7f1e4; font-weight: bold; }
    .banner { background: ${opts?.adversarial ? "#f8d7d3" : "#eef6ef"}; padding: 8px 12px; margin-bottom: 18px; }
  </style>
</head>
<body>
  ${opts?.adversarial ? `<div class="banner">MODIFIED COPY — not the approved instrument.</div>` : ""}
  <h1>${manifest.title.toUpperCase()}</h1>
  <p class="meta">Vendor agreement generated from a SignGate Intent Manifest</p>
  <h2>Parties</h2>
  <table>
    <tr><td class="label">Customer</td><td>${manifest.parties.customer}</td></tr>
    <tr><td class="label">Vendor</td><td>${manifest.parties.vendor}</td></tr>
  </table>
  <h2>1. Commercial terms</h2>
  <p>1.1 Contract Value. The total contract value is <strong>${value}</strong>.</p>
  <p>1.2 Term. This Agreement shall remain in force for <strong>${manifest.commercial_terms.term_months} months</strong>.</p>
  <p>1.3 Payment. Invoices are payable within <strong>${manifest.commercial_terms.payment_terms_days} days</strong>.</p>
  <p>1.4 Services. Vendor shall provide ${manifest.commercial_terms.services_description}.</p>
  <h2>2. Termination and renewal</h2>
  <p>2.1 Either party may terminate this Agreement by providing <strong>${manifest.legal_terms.termination_notice_days} days</strong> written notice.</p>
  <p>2.2 ${renew}</p>
  <h2>3. Legal terms</h2>
  <p>3.1 Governing Law. This Agreement is governed by the laws of <strong>${manifest.legal_terms.governing_law}</strong>.</p>
  <p>3.2 Liability. ${guarantee}</p>
  <p>3.3 Exclusivity. ${exclusive}</p>
  <h2>4. Payment destination</h2>
  <p>Account name: ${manifest.bank_details.account_name ?? "—"}</p>
  <p>Bank: ${manifest.bank_details.bank_name ?? "—"}</p>
  <p>Account number: ${manifest.bank_details.account_number ?? "—"}</p>
  ${sow ? `<h2>Schedule A — Statement of Work</h2>
  <p>This Statement of Work is attached to and forms part of the Agreement.</p>
  <p>Scope: ingest, transform, and serve analytics datasets for Customer, including monthly operational reporting.</p>
  <p>Deliverables: production pipeline, documentation, and a named technical contact.</p>` : ""}
  <h2>Signature</h2>
  <p>Signed by: ${manifest.signer.name}, ${manifest.signer.title}</p>
  <p>Email: ${manifest.signer.email}</p>
  <pre>--- SIGNGATE INTENT FIELDS ---
document_type: ${manifest.document_type}
customer: ${manifest.parties.customer}
vendor: ${manifest.parties.vendor}
contract_value_amount: ${manifest.commercial_terms.contract_value.amount}
contract_value_currency: ${manifest.commercial_terms.contract_value.currency}
term_months: ${manifest.commercial_terms.term_months}
payment_terms_days: ${manifest.commercial_terms.payment_terms_days}
termination_notice_days: ${manifest.legal_terms.termination_notice_days}
auto_renewal: ${manifest.legal_terms.auto_renewal}
personal_guarantee: ${manifest.legal_terms.personal_guarantee}
exclusivity: ${manifest.legal_terms.exclusivity}
governing_law: ${manifest.legal_terms.governing_law}
attachments: ${manifest.required_attachments.join(", ")}
bank_account: ${manifest.bank_details.account_number ?? ""}
bank_account_name: ${manifest.bank_details.account_name ?? ""}
bank_name: ${manifest.bank_details.bank_name ?? ""}
--- END SIGNGATE INTENT FIELDS ---</pre>
</body>
</html>`;
}

export async function generateAgreementPdf(
  manifest: IntentManifest,
  opts?: { adversarial?: boolean },
): Promise<{ buffer: Buffer; pageCount: number }> {
  const value = money(manifest);
  const includeSow = manifest.required_attachments.includes("Statement of Work");
  const buffer = await collectPdf((doc) => {
    header(
      doc,
      manifest.title.toUpperCase(),
      opts?.adversarial
        ? "Modified copy — not the approved instrument"
        : "Prepared from an approved Intent Manifest",
    );

    doc.font("Times-Bold").fontSize(12).fillColor("#1B1A16").text("Parties");
    doc.moveDown(0.3);
    doc.font("Times-Roman").fontSize(11);
    doc.text(`Customer: ${manifest.parties.customer}`);
    doc.text(`Vendor: ${manifest.parties.vendor}`);
    doc.moveDown(0.8);

    doc.font("Times-Bold").fontSize(12).text("1. Commercial terms");
    doc.moveDown(0.3).font("Times-Roman").fontSize(11);
    doc.text(`1.1 Contract Value. The total contract value is ${value}.`);
    doc.text(
      `1.2 Term. This Agreement shall remain in force for ${manifest.commercial_terms.term_months} months from the Effective Date.`,
    );
    doc.text(
      `1.3 Payment. Vendor shall invoice monthly. Invoices are payable within ${manifest.commercial_terms.payment_terms_days} days.`,
    );
    doc.text(
      `1.4 Services. Vendor shall provide ${manifest.commercial_terms.services_description} as further described in any attached schedules.`,
    );

    doc.addPage();
    header(doc, manifest.title.toUpperCase(), "Legal terms");
    doc.font("Times-Bold").fontSize(12).text("2. Termination and renewal");
    doc.moveDown(0.3).font("Times-Roman").fontSize(11);
    doc.text(
      `2.1 Either party may terminate this Agreement by providing ${manifest.legal_terms.termination_notice_days} days written notice to the other party.`,
    );
    doc.moveDown(0.4);
    if (manifest.legal_terms.auto_renewal) {
      doc.text(
        `2.2 This Agreement automatically renews for successive ${manifest.commercial_terms.term_months}-month periods unless either party provides ${manifest.legal_terms.termination_notice_days} days written notice of non-renewal.`,
      );
    } else {
      doc.text(
        "2.2 This Agreement does not automatically renew. Any extension requires a new written instrument signed by both parties.",
      );
    }

    doc.moveDown(0.8).font("Times-Bold").fontSize(12).text("3. Governing law and liability");
    doc.moveDown(0.3).font("Times-Roman").fontSize(11);
    doc.text(
      `3.1 Governing Law. This Agreement is governed by the laws of ${manifest.legal_terms.governing_law}, without regard to conflict-of-law principles.`,
    );
    doc.moveDown(0.4);
    if (manifest.legal_terms.personal_guarantee) {
      doc.text(
        `3.2 Personal Guarantee. The undersigned individual personally guarantees the Customer's obligations under this Agreement.`,
      );
    } else {
      doc.text(
        "3.2 Liability. Neither party provides a personal guarantee. No personal liability is assumed by any director, officer, or employee.",
      );
    }
    doc.moveDown(0.4);
    if (manifest.legal_terms.exclusivity) {
      doc.text("3.3 Exclusivity. Customer hereby appoints Vendor as its exclusive provider of the Services.");
    } else {
      doc.text(
        "3.3 Exclusivity. This Agreement does not grant exclusivity. Customer may obtain similar services from other vendors.",
      );
    }

    doc.moveDown(0.8).font("Times-Bold").fontSize(12).text("4. Payment destination");
    doc.moveDown(0.3).font("Times-Roman").fontSize(11);
    doc.text(`Account name: ${manifest.bank_details.account_name ?? "—"}`);
    doc.text(`Bank: ${manifest.bank_details.bank_name ?? "—"}`);
    doc.text(`Account number: ${manifest.bank_details.account_number ?? "—"}`);

    if (includeSow) {
      doc.addPage();
      header(doc, "Schedule A — Statement of Work", "Required attachment");
      doc.font("Times-Roman").fontSize(11);
      doc.text("This Statement of Work is attached to and forms part of the Agreement.");
      doc.moveDown(0.5);
      doc.text(
        `Vendor will deliver ${manifest.commercial_terms.services_description} for ${manifest.parties.customer}.`,
      );
      doc.moveDown(0.4);
      doc.text("Deliverables include a production data pipeline, operational documentation, and a named technical contact.");
      doc.moveDown(0.4);
      doc.text(`Fees under this Statement of Work are included in the contract value of ${value}.`);
    }

    doc.addPage();
    header(doc, "Signature block", "Human authorization required");
    doc.font("Times-Roman").fontSize(11);
    doc.text("This document may be prepared by an agent. It becomes legally real only when a human signs after SignGate verification.");
    doc.moveDown(1);
    doc.text(`Signed by: ${manifest.signer.name}`);
    doc.text(`Title: ${manifest.signer.title}`);
    doc.text(`Email: ${manifest.signer.email}`);
    doc.moveDown(1.2);
    doc.text("Signature: ________________________________");
    doc.moveDown(0.8);
    doc.text("Date: ________________________________");
    doc.moveDown(1.4);
    doc.font("Courier").fontSize(8).fillColor("#333").text("--- SIGNGATE INTENT FIELDS ---");
    const fields = [
      `document_type: ${manifest.document_type}`,
      `customer: ${manifest.parties.customer}`,
      `vendor: ${manifest.parties.vendor}`,
      `contract_value_amount: ${manifest.commercial_terms.contract_value.amount}`,
      `contract_value_currency: ${manifest.commercial_terms.contract_value.currency}`,
      `term_months: ${manifest.commercial_terms.term_months}`,
      `payment_terms_days: ${manifest.commercial_terms.payment_terms_days}`,
      `termination_notice_days: ${manifest.legal_terms.termination_notice_days}`,
      `auto_renewal: ${manifest.legal_terms.auto_renewal}`,
      `personal_guarantee: ${manifest.legal_terms.personal_guarantee}`,
      `exclusivity: ${manifest.legal_terms.exclusivity}`,
      `governing_law: ${manifest.legal_terms.governing_law}`,
      `attachments: ${manifest.required_attachments.join(", ")}`,
      `bank_account: ${manifest.bank_details.account_number ?? ""}`,
      `bank_account_name: ${manifest.bank_details.account_name ?? ""}`,
      `bank_name: ${manifest.bank_details.bank_name ?? ""}`,
    ];
    for (const line of fields) doc.text(line);
    doc.text("--- END SIGNGATE INTENT FIELDS ---");

    const range = doc.bufferedPageRange();
    for (let i = 0; i < range.count; i += 1) {
      doc.switchToPage(i);
      footer(doc, i + 1, range.count);
    }
  });

  return { buffer, pageCount: includeSow ? 4 : 3 };
}

export async function generateReceiptPdf(input: {
  documentId: string;
  title: string;
  gate: string;
  checksum: string;
  actor: string;
  findings: string[];
}): Promise<Buffer> {
  return collectPdf((doc) => {
    header(doc, "SignGate audit receipt", input.documentId);
    doc.font("Times-Roman").fontSize(11).fillColor("#1B1A16");
    doc.text(`Document: ${input.title}`);
    doc.text(`Gate: ${input.gate.toUpperCase()}`);
    doc.text(`Semantic checksum: ${input.checksum}`);
    doc.text(`Actor: ${input.actor}`);
    doc.text(`Issued: ${new Date().toISOString()}`);
    doc.moveDown();
    doc.font("Times-Bold").text("Findings");
    doc.font("Times-Roman");
    if (input.findings.length === 0) {
      doc.text("No material or critical discrepancies. The final document matched the approved Intent Manifest.");
    } else {
      for (const finding of input.findings) doc.text(`• ${finding}`);
    }
  });
}
