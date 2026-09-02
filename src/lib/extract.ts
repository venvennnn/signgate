import type { ExtractedTerms, IntentManifest, Money } from "./types";

type PageHit = { page: number; excerpt: string; matched: string; value: string | null };

function collapse(text: string) {
  return text.replace(/\s+/g, " ").trim();
}

function pageOf(pages: string[], pattern: RegExp): PageHit | null {
  for (let i = 0; i < pages.length; i += 1) {
    const match = pages[i].match(pattern);
    if (match) {
      const idx = match.index ?? 0;
      const excerpt = collapse(pages[i].slice(Math.max(0, idx - 40), idx + match[0].length + 80));
      const captured = (match[1] ?? "").trim();
      return { page: i + 1, excerpt, matched: match[0], value: captured || null };
    }
  }
  return null;
}

function findLabeled(pages: string[], label: string): PageHit | null {
  const pattern = new RegExp(`${label}[:\\s]+([^\\n]{2,80})`, "i");
  return pageOf(pages, pattern);
}

function parseMoney(raw: string): Money | null {
  const match = raw.match(/(USD|SGD|EUR|GBP|US\$|S\$|\$)\s*([\d,]+(?:\.\d{1,2})?)/i) ??
    raw.match(/([\d,]+(?:\.\d{1,2})?)\s*(USD|dollars)/i);
  if (!match) return null;
  const amount = Number((match[2] ?? match[1]).replace(/,/g, ""));
  if (!Number.isFinite(amount)) return null;
  const token = (match[1] ?? match[2] ?? "USD").toUpperCase();
  const currency = token === "$" || token === "US$" || token === "DOLLARS" ? "USD" : token.replace("$", "");
  return { amount, currency: currency || "USD" };
}

function parseDays(raw: string | null): number | null {
  if (!raw) return null;
  const match = raw.match(/(\d+)\s*day/i);
  return match ? Number(match[1]) : null;
}

function parseMonths(raw: string | null): number | null {
  if (!raw) return null;
  const months = raw.match(/(\d+)\s*month/i);
  if (months) return Number(months[1]);
  const years = raw.match(/(\d+)\s*year/i);
  if (years) return Number(years[1]) * 12;
  if (/one[-\s]year|twelve months/i.test(raw)) return 12;
  return null;
}

function polarity(text: string, positive: RegExp, negative: RegExp): boolean | null {
  const lower = text.toLowerCase();
  const neg = negative.test(lower);
  const pos = positive.test(lower);
  if (neg) return false;
  if (pos) return true;
  return null;
}

function machineBlock(pages: string[]) {
  const joined = pages.join("\n");
  const block = joined.match(/--- SIGNGATE INTENT FIELDS ---([\s\S]*?)--- END SIGNGATE INTENT FIELDS ---/);
  if (!block) return null;
  const fields: Record<string, string> = {};
  for (const line of block[1].split("\n")) {
    const idx = line.indexOf(":");
    if (idx === -1) continue;
    fields[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
  }
  return fields;
}

function boolField(value: string | undefined): boolean | null {
  if (value == null) return null;
  if (["true", "yes", "1"].includes(value.toLowerCase())) return true;
  if (["false", "no", "0"].includes(value.toLowerCase())) return false;
  return null;
}

export function extractTermsFromPages(pages: string[]): ExtractedTerms {
  const joined = pages.join("\n\n");
  const machine = machineBlock(pages);
  const fieldPages: Record<string, number | null> = {};
  const excerpts: Record<string, string> = {};

  const remember = (field: string, hit: PageHit | null) => {
    if (!hit) return;
    fieldPages[field] = hit.page;
    excerpts[field] = hit.excerpt;
  };

  const contractHit =
    pageOf(pages, /(?:contract value|total (?:contract )?value|fees payable)[^\n]{0,40}((?:USD|SGD|EUR|GBP|\$)\s*[\d,]+)/i) ??
    pageOf(pages, /(?:USD|\$)\s*[\d,]{3,}/);
  remember("contract_value", contractHit);

  const termHit =
    pageOf(pages, /(?:term of (?:this )?agreement|shall remain in force for|duration)[^\n]{0,40}/i) ??
    pageOf(pages, /\b\d+\s*months?\b/i);
  remember("term_months", termHit);

  const payHit = pageOf(pages, /(?:payable within|payment terms|net)\s*\d+\s*days/i);
  remember("payment_terms_days", payHit);

  const termNoticeHit = pageOf(
    pages,
    /(?:terminat\w+|written notice)[^\n]{0,80}\d+\s*days|\d+\s*days[^\n]{0,40}(?:written )?notice/i,
  );
  remember("termination_notice_days", termNoticeHit);

  const renewHit =
    pageOf(pages, /does not automatically renew|no automatic renewal|automatically renews?/i) ??
    pageOf(pages, /renewal/i);
  remember("auto_renewal", renewHit);

  const lawHit = pageOf(pages, /governed by the laws of [A-Za-z ]+|governing law[^\n]{0,40}/i);
  remember("governing_law", lawHit);

  const guaranteeHit = pageOf(pages, /personal(?:ly)?\s+(?:guarantee|liable|liability)/i);
  remember("personal_guarantee", guaranteeHit);

  const exclusiveHit = pageOf(pages, /exclusiv(?:e|ity)/i);
  remember("exclusivity", exclusiveHit);

  const customerHit = findLabeled(pages, "Customer") ?? pageOf(pages, /Customer[:\s]+([A-Z][^\n]{2,60})/);
  remember("customer", customerHit);
  const vendorHit = findLabeled(pages, "Vendor") ?? pageOf(pages, /Vendor[:\s]+([A-Z][^\n]{2,60})/);
  remember("vendor", vendorHit);

  const bankHit = pageOf(pages, /account(?: number)?[:\s]+[0-9-]+/i);
  remember("bank_account", bankHit);

  let contract_value: Money | null = null;
  if (machine?.contract_value_amount) {
    contract_value = {
      amount: Number(machine.contract_value_amount),
      currency: machine.contract_value_currency ?? "USD",
    };
  } else if (contractHit) {
    contract_value = parseMoney(contractHit.excerpt);
  }

  const term_months = machine?.term_months
    ? Number(machine.term_months)
    : parseMonths(termHit?.matched ?? termHit?.excerpt ?? joined.match(/remain in force for ([^\n.]+)/i)?.[1] ?? null);

  const payment_terms_days = machine?.payment_terms_days
    ? Number(machine.payment_terms_days)
    : parseDays(payHit?.matched ?? payHit?.excerpt ?? joined.match(/payable within ([^\n.]+)/i)?.[0] ?? null);

  const termination_notice_days = machine?.termination_notice_days
    ? Number(machine.termination_notice_days)
    : parseDays(termNoticeHit?.matched ?? termNoticeHit?.excerpt ?? null);

  const auto_renewal =
    boolField(machine?.auto_renewal) ??
    polarity(
      joined,
      /automatically renews?(?:\s+for)?/i,
      /does not automatically renew|no automatic renewal|shall not automatically renew|without automatic renewal/i,
    );

  const personal_guarantee =
    boolField(machine?.personal_guarantee) ??
    polarity(
      joined,
      /personal(?:ly)?\s+(?:guarantees?|liable|liability)(?!\s+is not)/i,
      /no personal(?:ly)?\s+(?:guarantee|liability)|does not (?:provide|include) a personal guarantee|neither party provides a personal guarantee/i,
    );

  const exclusivity =
    boolField(machine?.exclusivity) ??
    polarity(
      joined,
      /exclusive(?:ly)?(?:\s+vendor|\s+supplier|\s+provider)?|exclusivity/i,
      /no exclusivity|not exclusive|non-exclusive|does not grant exclusivity/i,
    );

  let governing_law: string | null = machine?.governing_law ?? null;
  if (!governing_law) {
    const law = joined.match(/governed by the laws of ([A-Za-z ]{2,40}?)(?:\.|,|;|\n)/i);
    governing_law = law?.[1]?.trim() ?? null;
  }

  const cleanParty = (value: string) =>
    value
      .replace(/\s+\d+(\.\d+)?\s.*$/, "")
      .replace(/\s+(Customer|Vendor|Contract|Account)\b.*$/i, "")
      .trim();

  let customer = machine?.customer ?? null;
  if (!customer && (customerHit?.value || customerHit?.matched)) {
    customer = cleanParty(
      (customerHit.value ?? customerHit.matched.replace(/^.*?Customer[:\s]+/i, "")).split(/[.\n]/)[0],
    );
  }
  let vendor = machine?.vendor ?? null;
  if (!vendor && (vendorHit?.value || vendorHit?.matched)) {
    vendor = cleanParty(
      (vendorHit.value ?? vendorHit.matched.replace(/^.*?Vendor[:\s]+/i, "")).split(/[.\n]/)[0],
    );
  }

  const attachments_found: string[] = [];
  if (/statement of work/i.test(joined) || machine?.attachments?.toLowerCase().includes("statement of work")) {
    attachments_found.push("Statement of Work");
  }
  if (/service level agreement|\bSLA\b/.test(joined)) {
    attachments_found.push("Service Level Agreement");
  }

  const account = machine?.bank_account ?? joined.match(/account(?: number)?[:\s]+([0-9-]+)/i)?.[1] ?? null;
  const accountName = machine?.bank_account_name ?? joined.match(/account name[:\s]+([^\n]+)/i)?.[1]?.trim() ?? null;
  const bankName = machine?.bank_name ?? joined.match(/bank[:\s]+([A-Za-z0-9 .]+)/i)?.[1]?.trim() ?? null;

  const signer_names = [...joined.matchAll(/Signed by[:\s]+([A-Z][^\n]{2,60})/g)].map((m) => m[1].trim());

  return {
    parties: { customer, vendor },
    commercial_terms: {
      contract_value,
      term_months: Number.isFinite(term_months as number) ? term_months : null,
      payment_terms_days: Number.isFinite(payment_terms_days as number) ? payment_terms_days : null,
    },
    legal_terms: {
      termination_notice_days: Number.isFinite(termination_notice_days as number)
        ? termination_notice_days
        : null,
      auto_renewal,
      governing_law,
      personal_guarantee,
      exclusivity,
    },
    attachments_found,
    bank_details: {
      account_name: accountName,
      account_number: account,
      bank_name: bankName,
    },
    signer_names,
    page_count: pages.length,
    field_pages: fieldPages,
    excerpts,
    raw_text: joined,
  };
}

export function pagesFromManifestPreview(manifest: IntentManifest): string[] {
  return [JSON.stringify(manifest)];
}
