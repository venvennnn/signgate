import type { IntentManifest } from "./types";

const CURRENCY_SYMBOLS: Record<string, string> = {
  $: "USD",
  "€": "EUR",
  "£": "GBP",
  "¥": "JPY",
  "s$": "SGD",
};

const WORD_MONTHS: Record<string, number> = {
  one: 12,
  a: 12,
  two: 24,
  three: 36,
};

export const DEFAULT_PROMPT =
  "Create a one-year data-services agreement for $50,000, with 30-day termination and no automatic renewal.";

export function defaultManifest(): IntentManifest {
  return {
    document_type: "vendor_agreement",
    title: "Data Services Agreement",
    parties: {
      customer: "Northstar Analytics",
      vendor: "Atlas Systems",
    },
    commercial_terms: {
      contract_value: { amount: 50_000, currency: "USD" },
      term_months: 12,
      payment_terms_days: 30,
      services_description: "data processing, analytics pipeline, and related professional services",
    },
    legal_terms: {
      termination_notice_days: 30,
      auto_renewal: false,
      governing_law: "Singapore",
      personal_guarantee: false,
      exclusivity: false,
    },
    required_attachments: ["Statement of Work"],
    must_not_include: ["Exclusivity", "Automatic renewal", "Personal liability"],
    bank_details: {
      account_name: "Atlas Systems Pte. Ltd.",
      account_number: "001-4729183",
      bank_name: "DBS Bank",
    },
    signer: {
      name: "Priya Menon",
      email: "priya.menon@northstar.example",
      title: "Head of Legal Operations",
    },
  };
}

export function adversarialManifest(base: IntentManifest): IntentManifest {
  return {
    ...base,
    commercial_terms: {
      ...base.commercial_terms,
      contract_value: {
        amount: base.commercial_terms.contract_value.amount * 10,
        currency: base.commercial_terms.contract_value.currency,
      },
    },
    legal_terms: {
      ...base.legal_terms,
      termination_notice_days: 90,
      auto_renewal: true,
      personal_guarantee: false,
    },
    required_attachments: [],
    must_not_include: [],
  };
}

function parseAmount(raw: string): number {
  return Number(raw.replace(/,/g, ""));
}

function detectCurrency(prompt: string, amountMatch: string): string {
  const around = prompt.toLowerCase();
  if (/\bsgd\b|singapore dollar/.test(around)) return "SGD";
  if (/\beur\b|euro/.test(around)) return "EUR";
  if (/\bgbp\b|pound/.test(around)) return "GBP";
  const symbol = amountMatch.trim()[0];
  return CURRENCY_SYMBOLS[symbol] ?? "USD";
}

function extractParty(prompt: string, role: "vendor" | "customer"): string | null {
  const patterns =
    role === "vendor"
      ? [
          /(?:with|vendor|supplier|provider)\s+([A-Z][A-Za-z0-9&.\- ]{2,40}?)(?:\s+for|\s+at|\s*,|\s*\.|$)/,
          /(?:and)\s+([A-Z][A-Za-z0-9&.\- ]{2,40}?)\s+(?:as )?(?:the )?vendor/,
        ]
      : [
          /(?:customer|client|buyer)\s+([A-Z][A-Za-z0-9&.\- ]{2,40}?)(?:\s+and|\s+with|\s*,|\s*\.|$)/,
          /(?:for)\s+([A-Z][A-Za-z0-9&.\- ]{2,40}?)\s+(?:as )?(?:the )?customer/,
        ];
  for (const pattern of patterns) {
    const match = prompt.match(pattern);
    if (match?.[1]) return match[1].trim().replace(/\s+/g, " ");
  }
  return null;
}

export function extractIntent(prompt: string): IntentManifest {
  const manifest = defaultManifest();
  const text = prompt.trim() || DEFAULT_PROMPT;
  const lower = text.toLowerCase();

  const money =
    text.match(/(?:USD|SGD|EUR|GBP|US\$|S\$|\$|€|£)\s*([\d,]+(?:\.\d{1,2})?)/i) ??
    text.match(/([\d,]+(?:\.\d{1,2})?)\s*(?:USD|dollars)/i);
  if (money) {
    const amount = parseAmount(money[1]);
    if (Number.isFinite(amount) && amount > 0) {
      manifest.commercial_terms.contract_value = {
        amount,
        currency: detectCurrency(text, money[0]),
      };
    }
  }

  const months = lower.match(/(\d+)\s*[-\s]?month/);
  const years = lower.match(/(\d+)\s*[-\s]?year/) ?? lower.match(/\b(one|a|two|three)[-\s]year/);
  if (months) {
    manifest.commercial_terms.term_months = Number(months[1]);
  } else if (years) {
    const token = years[1];
    manifest.commercial_terms.term_months = WORD_MONTHS[token] ?? Number(token) * 12;
  }

  const notice =
    lower.match(/(\d+)[-\s]?day(?:s)?(?:\s+(?:written\s+)?)?(?:termination|notice|cancel)/) ??
    lower.match(/(?:terminat\w+|cancel\w+|notice).{0,24}(\d+)[-\s]?day/);
  if (notice) {
    manifest.legal_terms.termination_notice_days = Number(notice[1]);
  }

  const payment = lower.match(/(\d+)[-\s]?day(?:s)?\s+(?:payment|net)/) ?? lower.match(/net\s*(\d+)/);
  if (payment) {
    manifest.commercial_terms.payment_terms_days = Number(payment[1]);
  }

  if (/\bno(?:t)?\s+(?:automatic(?:ally)?\s+)?renew/.test(lower) || /without\s+auto(?:matic)?[-\s]?renew/.test(lower)) {
    manifest.legal_terms.auto_renewal = false;
    if (!manifest.must_not_include.includes("Automatic renewal")) {
      manifest.must_not_include.push("Automatic renewal");
    }
  } else if (/auto(?:matic(?:ally)?)?\s+renew/.test(lower)) {
    manifest.legal_terms.auto_renewal = true;
    manifest.must_not_include = manifest.must_not_include.filter((item) => item !== "Automatic renewal");
  }

  if (/personal(?:ly)?\s+(?:guarantee|liable|liability)/.test(lower)) {
    const negated = /no\s+personal(?:ly)?\s+(?:guarantee|liab)/.test(lower);
    manifest.legal_terms.personal_guarantee = !negated;
  }

  if (/\bexclusiv/.test(lower)) {
    manifest.legal_terms.exclusivity = !/\bno(?:t)?\s+exclusiv/.test(lower);
  }

  const law = text.match(
    /(?:governed by|governing law(?:\s+of)?|under(?: the)? laws of)\s+([A-Z][A-Za-z ]{2,40}?)(?:\.|,|$)/i,
  );
  if (law?.[1]) {
    manifest.legal_terms.governing_law = law[1].trim();
  } else if (/singapore/.test(lower)) {
    manifest.legal_terms.governing_law = "Singapore";
  }

  const vendor = extractParty(text, "vendor");
  const customer = extractParty(text, "customer");
  if (vendor) manifest.parties.vendor = vendor;
  if (customer) manifest.parties.customer = customer;

  if (/statement of work|sow/.test(lower)) {
    if (!manifest.required_attachments.includes("Statement of Work")) {
      manifest.required_attachments.push("Statement of Work");
    }
  }

  if (/data[-\s]?services?/.test(lower)) {
    manifest.title = "Data Services Agreement";
    manifest.commercial_terms.services_description =
      "data processing, analytics pipeline, and related professional services";
  } else if (/vendor/.test(lower)) {
    manifest.title = "Vendor Agreement";
  }

  const email = text.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
  if (email) manifest.signer.email = email[0];

  return manifest;
}
