import { extractText } from "unpdf";
import { extractTermsFromPages } from "./extract";
import type { ExtractedTerms } from "./types";

export async function extractPdfTerms(buffer: Buffer): Promise<ExtractedTerms> {
  const data = new Uint8Array(buffer);
  const result = await extractText(data, { mergePages: false });
  const pages = Array.isArray(result.text) ? result.text.map((page) => page || "") : [String(result.text ?? "")];
  const cleaned = pages.map((page) => page.replace(/\u0000/g, " ").replace(/[ \t]+\n/g, "\n"));
  return extractTermsFromPages(cleaned.length ? cleaned : [""]);
}
