/**
 * Foxit PDF Services + eSign adapters.
 *
 * When credentials are absent, callers must use local generation/extraction.
 * The LLM / agent never bypasses the signature gate by talking to eSign directly.
 */

export type FoxitTaskStatus = {
  status: string;
  resultDocumentId?: string;
  error?: unknown;
};

export function foxitConfigured() {
  return Boolean(process.env.FOXIT_CLIENT_ID && process.env.FOXIT_CLIENT_SECRET);
}

function host() {
  return (process.env.FOXIT_API_HOST || "https://na1.fusion.foxit.com").replace(/\/$/, "");
}

function authHeaders(extra?: Record<string, string>) {
  return {
    client_id: process.env.FOXIT_CLIENT_ID || "",
    client_secret: process.env.FOXIT_CLIENT_SECRET || "",
    ...extra,
  };
}

async function pollTask(taskId: string, timeoutMs = 60_000): Promise<FoxitTaskStatus> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const res = await fetch(`${host()}/pdf-services/api/tasks/${taskId}`, {
      headers: authHeaders({ "Content-Type": "application/json" }),
    });
    if (!res.ok) {
      throw new Error(`Foxit task poll failed: ${res.status} ${await res.text()}`);
    }
    const body = (await res.json()) as FoxitTaskStatus;
    if (body.status === "COMPLETED") return body;
    if (body.status === "FAILED") {
      throw new Error(`Foxit task failed: ${JSON.stringify(body.error ?? body)}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  throw new Error("Foxit task timed out");
}

async function downloadDocument(documentId: string): Promise<Buffer> {
  const res = await fetch(`${host()}/pdf-services/api/documents/${documentId}/download`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Foxit download failed: ${res.status} ${await res.text()}`);
  return Buffer.from(await res.arrayBuffer());
}

async function uploadDocument(filename: string, bytes: Buffer, mime: string): Promise<string> {
  const form = new FormData();
  form.append("file", new Blob([new Uint8Array(bytes)], { type: mime }), filename);
  const res = await fetch(`${host()}/pdf-services/api/documents/upload`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  if (!res.ok) throw new Error(`Foxit upload failed: ${res.status} ${await res.text()}`);
  const body = (await res.json()) as { documentId: string };
  return body.documentId;
}

export async function foxitHtmlToPdf(html: string): Promise<Buffer> {
  const documentId = await uploadDocument("agreement.html", Buffer.from(html, "utf8"), "text/html");
  const create = await fetch(`${host()}/pdf-services/api/documents/create/pdf-from-html`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ documentId }),
  });
  if (!create.ok) throw new Error(`Foxit HTML→PDF failed: ${create.status} ${await create.text()}`);
  const { taskId } = (await create.json()) as { taskId: string };
  const done = await pollTask(taskId);
  if (!done.resultDocumentId) throw new Error("Foxit HTML→PDF completed without resultDocumentId");
  return downloadDocument(done.resultDocumentId);
}

export async function foxitPdfToText(pdf: Buffer): Promise<string> {
  const documentId = await uploadDocument("document.pdf", pdf, "application/pdf");
  const create = await fetch(`${host()}/pdf-services/api/documents/convert/pdf-to-text`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ documentId }),
  });
  if (!create.ok) throw new Error(`Foxit PDF→text failed: ${create.status} ${await create.text()}`);
  const { taskId } = (await create.json()) as { taskId: string };
  const done = await pollTask(taskId);
  if (!done.resultDocumentId) throw new Error("Foxit PDF→text completed without resultDocumentId");
  const buf = await downloadDocument(done.resultDocumentId);
  return buf.toString("utf8");
}

export type EsignResult = {
  provider: "foxit" | "simulated";
  provider_ref: string | null;
  raw: unknown;
};

export async function foxitCreateEnvelope(input: {
  folderName: string;
  signerEmail: string;
  signerName: string;
  fileUrl?: string;
  base64Pdf?: string;
}): Promise<EsignResult> {
  const [firstName, ...rest] = input.signerName.split(" ");
  const lastName = rest.join(" ") || "Signer";
  const body: Record<string, unknown> = {
    folderName: input.folderName,
    parties: [
      {
        firstName,
        lastName,
        emailId: input.signerEmail,
        permission: "FILL_FIELDS_AND_SIGN",
        sequence: 1,
      },
    ],
    fields: [
      {
        type: "signature",
        x: 72,
        y: 120,
        width: 160,
        height: 40,
        documentNumber: 1,
        pageNumber: 1,
        party: 1,
        required: true,
      },
    ],
    processTextTags: false,
    processAcroFields: false,
    createEmbeddedSigningSession: true,
    sendNow: true,
  };

  if (input.fileUrl) {
    body.inputType = "url";
    body.fileUrls = [input.fileUrl];
    body.fileNames = [`${input.folderName}.pdf`];
  } else if (input.base64Pdf) {
    body.inputType = "base64";
    body.base64FileString = input.base64Pdf;
    body.fileNames = [`${input.folderName}.pdf`];
  }

  const res = await fetch(`${host()}/esign/api/v1/folders/createfolder`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`Foxit eSign failed: ${res.status} ${await res.text()}`);
  }
  const raw = (await res.json()) as { folderId?: string; id?: string; folder?: { folderId?: string } };
  const ref = String(raw.folderId ?? raw.folder?.folderId ?? raw.id ?? "");
  return { provider: "foxit", provider_ref: ref || null, raw };
}
