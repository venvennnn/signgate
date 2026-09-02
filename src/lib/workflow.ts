import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { nanoid } from "nanoid";
import { checksumFromManifest, fingerprint } from "./checksum";
import { db, filesDir } from "./db";
import { extractTermsFromPages } from "./extract";
import { foxitConfigured, foxitCreateEnvelope, foxitHtmlToPdf, foxitPdfToText } from "./foxit";
import { adversarialManifest, extractIntent } from "./intent";
import { extractPdfTerms } from "./pdf-extract";
import { agreementHtml, generateAgreementPdf, generateReceiptPdf } from "./pdf";
import { proposeSemanticFindings } from "./semantic";
import type {
  AuditEvent,
  Discrepancy,
  DocumentRecord,
  DocumentStatus,
  ExtractedTerms,
  GateDecision,
  IntentManifest,
  ManifestRecord,
  SessionSnapshot,
  VersionRecord,
} from "./types";
import { decideGate } from "./verify";

function now() {
  return new Date().toISOString();
}

function parse<T>(value: string): T {
  return JSON.parse(value) as T;
}

function writeAudit(input: Omit<AuditEvent, "id" | "timestamp">) {
  db()
    .prepare(
      `INSERT INTO audit_events
        (id, document_id, actor, timestamp, document_hash, manifest_version, action, previous_state, new_state, reason, metadata)
       VALUES (@id, @document_id, @actor, @timestamp, @document_hash, @manifest_version, @action, @previous_state, @new_state, @reason, @metadata)`,
    )
    .run({
      id: nanoid(12),
      timestamp: now(),
      document_hash: input.document_hash,
      manifest_version: input.manifest_version,
      action: input.action,
      previous_state: input.previous_state,
      new_state: input.new_state,
      reason: input.reason,
      metadata: input.metadata ? JSON.stringify(input.metadata) : null,
      document_id: input.document_id,
      actor: input.actor,
    });
}

function getDocument(id: string): DocumentRecord {
  const row = db().prepare("SELECT * FROM documents WHERE id = ?").get(id) as DocumentRecord | undefined;
  if (!row) throw new Error("Document not found");
  return row;
}

function setStatus(id: string, status: DocumentStatus) {
  db().prepare("UPDATE documents SET status = ?, updated_at = ? WHERE id = ?").run(status, now(), id);
}

function latestManifest(documentId: string): ManifestRecord | null {
  const row = db()
    .prepare("SELECT * FROM intent_manifests WHERE document_id = ? ORDER BY version DESC LIMIT 1")
    .get(documentId) as Omit<ManifestRecord, "payload"> & { payload: string } | undefined;
  if (!row) return null;
  return { ...row, payload: parse<IntentManifest>(row.payload) };
}

function approvedManifest(documentId: string): ManifestRecord | null {
  const row = db()
    .prepare(
      "SELECT * FROM intent_manifests WHERE document_id = ? AND status = 'approved' ORDER BY version DESC LIMIT 1",
    )
    .get(documentId) as Omit<ManifestRecord, "payload"> & { payload: string } | undefined;
  if (!row) return null;
  return { ...row, payload: parse<IntentManifest>(row.payload) };
}

function currentVersion(documentId: string): VersionRecord | null {
  return (
    (db()
      .prepare("SELECT * FROM document_versions WHERE document_id = ? AND is_current = 1")
      .get(documentId) as VersionRecord | undefined) ?? null
  );
}

function latestDecision(documentId: string) {
  const row = db()
    .prepare("SELECT * FROM gate_decisions WHERE document_id = ? ORDER BY created_at DESC LIMIT 1")
    .get(documentId) as { payload: string } | undefined;
  return row ? parse<GateDecision>(row.payload) : null;
}

function latestExtracted(versionId: string | undefined) {
  if (!versionId) return null;
  const row = db()
    .prepare("SELECT payload FROM extracted_terms WHERE version_id = ? ORDER BY created_at DESC LIMIT 1")
    .get(versionId) as { payload: string } | undefined;
  return row ? parse<ExtractedTerms>(row.payload) : null;
}

function latestSignature(documentId: string) {
  const row = db()
    .prepare("SELECT * FROM signature_requests WHERE document_id = ? ORDER BY created_at DESC LIMIT 1")
    .get(documentId) as
    | {
        id: string;
        provider: string;
        provider_ref: string | null;
        signer_email: string;
        status: string;
        created_at: string;
      }
    | undefined;
  return row ?? null;
}

function auditTrail(documentId: string): AuditEvent[] {
  const rows = db()
    .prepare("SELECT * FROM audit_events WHERE document_id = ? ORDER BY timestamp ASC")
    .all(documentId) as Array<AuditEvent & { metadata: string | null }>;
  return rows.map((row) => ({
    ...row,
    metadata: row.metadata ? parse(row.metadata) : null,
  }));
}

export function getSession(id: string): SessionSnapshot {
  const document = getDocument(id);
  const version = currentVersion(id);
  const versions = db()
    .prepare("SELECT * FROM document_versions WHERE document_id = ? ORDER BY version ASC")
    .all(id) as VersionRecord[];
  return {
    document,
    manifest: latestManifest(id),
    approved_manifest: approvedManifest(id),
    current_version: version,
    versions,
    extracted: latestExtracted(version?.id),
    decision: latestDecision(id),
    signature_request: latestSignature(id),
    audit: auditTrail(id),
    foxit_configured: foxitConfigured(),
  };
}

export function listDocuments() {
  return db()
    .prepare("SELECT id, title, status, created_at, updated_at FROM documents ORDER BY updated_at DESC")
    .all() as Array<Pick<DocumentRecord, "id" | "title" | "status" | "created_at" | "updated_at">>;
}

export function createDocument(prompt: string, actor = "human:operator") {
  const manifest = extractIntent(prompt);
  const id = nanoid(10);
  const ts = now();
  db()
    .prepare(
      `INSERT INTO documents (id, title, document_type, status, prompt, actor, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .run(id, manifest.title, manifest.document_type, "awaiting_approval", prompt, actor, ts, ts);
  const manifestId = nanoid(12);
  db()
    .prepare(
      `INSERT INTO intent_manifests (id, document_id, version, payload, status, created_at)
       VALUES (?, ?, 1, ?, 'draft', ?)`,
    )
    .run(manifestId, id, JSON.stringify(manifest), ts);
  writeAudit({
    document_id: id,
    actor,
    document_hash: null,
    manifest_version: 1,
    action: "capture_intent",
    previous_state: null,
    new_state: "awaiting_approval",
    reason: "Plain-language request converted to an Intent Manifest. Not yet authorized.",
    metadata: { prompt },
  });
  return getSession(id);
}

export function updateDraftManifest(documentId: string, payload: IntentManifest, actor = "human:operator") {
  const current = latestManifest(documentId);
  if (!current) throw new Error("No manifest");
  if (current.status === "approved") {
    db()
      .prepare("UPDATE intent_manifests SET status = 'superseded' WHERE id = ?")
      .run(current.id);
  }
  const version = current.version + (current.status === "approved" ? 1 : 0);
  if (current.status === "draft") {
    db()
      .prepare("UPDATE intent_manifests SET payload = ? WHERE id = ?")
      .run(JSON.stringify(payload), current.id);
  } else {
    db()
      .prepare(
        `INSERT INTO intent_manifests (id, document_id, version, payload, status, created_at)
         VALUES (?, ?, ?, ?, 'draft', ?)`,
      )
      .run(nanoid(12), documentId, version, JSON.stringify(payload), now());
  }
  const doc = getDocument(documentId);
  setStatus(documentId, "awaiting_approval");
  db()
    .prepare("UPDATE documents SET title = ?, updated_at = ? WHERE id = ?")
    .run(payload.title, now(), documentId);
  writeAudit({
    document_id: documentId,
    actor,
    document_hash: null,
    manifest_version: version,
    action: "edit_manifest",
    previous_state: doc.status,
    new_state: "awaiting_approval",
    reason: "Human edited the structured terms before approval.",
    metadata: null,
  });
  return getSession(documentId);
}

export function approveManifest(documentId: string, actor = "human:operator", notes?: string) {
  const manifest = latestManifest(documentId);
  if (!manifest) throw new Error("No manifest to approve");
  db().prepare("UPDATE intent_manifests SET status = 'approved' WHERE id = ?").run(manifest.id);
  db()
    .prepare(
      `INSERT INTO manifest_approvals (id, manifest_id, actor, approved_at, notes) VALUES (?, ?, ?, ?, ?)`,
    )
    .run(nanoid(12), manifest.id, actor, now(), notes ?? null);
  const previous = getDocument(documentId).status;
  setStatus(documentId, "approved");
  writeAudit({
    document_id: documentId,
    actor,
    document_hash: fingerprint(checksumFromManifest(manifest.payload)),
    manifest_version: manifest.version,
    action: "approve_manifest",
    previous_state: previous,
    new_state: "approved",
    reason: "Human authorized the Intent Manifest. This is now the source of truth.",
    metadata: { notes: notes ?? null },
  });
  return getSession(documentId);
}

async function persistVersion(input: {
  documentId: string;
  source: VersionRecord["source"];
  buffer: Buffer;
  pageCount: number;
  notes?: string;
  actor: string;
}) {
  const previous = currentVersion(input.documentId);
  const version = (previous?.version ?? 0) + 1;
  const sha256 = createHash("sha256").update(input.buffer).digest("hex");
  const dir = path.join(filesDir(), input.documentId);
  fs.mkdirSync(dir, { recursive: true });
  const filePath = path.join(dir, `v${version}.pdf`);
  fs.writeFileSync(filePath, input.buffer);
  db().prepare("UPDATE document_versions SET is_current = 0 WHERE document_id = ?").run(input.documentId);
  const id = nanoid(12);
  db()
    .prepare(
      `INSERT INTO document_versions
        (id, document_id, version, source, file_path, sha256, page_count, created_at, is_current, notes)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)`,
    )
    .run(
      id,
      input.documentId,
      version,
      input.source,
      filePath,
      sha256,
      input.pageCount,
      now(),
      input.notes ?? null,
    );
  writeAudit({
    document_id: input.documentId,
    actor: input.actor,
    document_hash: sha256,
    manifest_version: latestManifest(input.documentId)?.version ?? null,
    action: `add_version:${input.source}`,
    previous_state: getDocument(input.documentId).status,
    new_state: getDocument(input.documentId).status,
    reason: input.notes ?? `Stored document version ${version} from ${input.source}.`,
    metadata: { version_id: id, page_count: input.pageCount },
  });
  return { id, sha256, version, filePath };
}

async function extractFromBuffer(buffer: Buffer): Promise<ExtractedTerms> {
  if (foxitConfigured()) {
    try {
      const text = await foxitPdfToText(buffer);
      const pages = text.split(/\f|\n{4,}/).filter(Boolean);
      return extractTermsFromPages(pages.length ? pages : [text]);
    } catch {
      return extractPdfTerms(buffer);
    }
  }
  return extractPdfTerms(buffer);
}

export async function generateDocument(documentId: string, actor = "human:operator") {
  const approved = approvedManifest(documentId);
  if (!approved) throw new Error("Approve the Intent Manifest before generating a document.");
  let buffer: Buffer;
  let pageCount: number;
  let via = "local_pdfkit";
  if (foxitConfigured()) {
    try {
      buffer = await foxitHtmlToPdf(agreementHtml(approved.payload));
      const extractedProbe = await extractFromBuffer(buffer);
      pageCount = extractedProbe.page_count || 3;
      via = "foxit_html_to_pdf";
    } catch {
      const local = await generateAgreementPdf(approved.payload);
      buffer = local.buffer;
      pageCount = local.pageCount;
      via = "local_pdfkit_fallback";
    }
  } else {
    const local = await generateAgreementPdf(approved.payload);
    buffer = local.buffer;
    pageCount = local.pageCount;
  }
  await persistVersion({
    documentId,
    source: "generated",
    buffer,
    pageCount,
    notes: `Generated via ${via}`,
    actor,
  });
  setStatus(documentId, "generated");
  return verifyCurrent(documentId, actor, `Generated document compared to approved manifest (${via}).`);
}

export async function uploadDocument(
  documentId: string,
  buffer: Buffer,
  actor = "human:operator",
  source: VersionRecord["source"] = "uploaded",
  notes?: string,
) {
  if (!approvedManifest(documentId)) {
    throw new Error("Approve the Intent Manifest before verifying a document.");
  }
  const probe = await extractFromBuffer(buffer);
  await persistVersion({
    documentId,
    source,
    buffer,
    pageCount: probe.page_count || 1,
    notes,
    actor,
  });
  return verifyCurrent(documentId, actor, notes ?? "Uploaded document compared to approved manifest.");
}

export async function introduceAdversary(documentId: string, actor = "human:operator") {
  const approved = approvedManifest(documentId);
  if (!approved) throw new Error("Approve and generate an agreement before introducing an adversarial edit.");
  const tampered = adversarialManifest(approved.payload);
  const pdf = await generateAgreementPdf(tampered, { adversarial: true });
  return uploadDocument(
    documentId,
    pdf.buffer,
    actor,
    "adversarial",
    "Adversarial edit: value ×10, 90-day termination, automatic renewal inserted, Statement of Work removed.",
  );
}

export async function restoreApproved(documentId: string, actor = "human:operator") {
  const generated = db()
    .prepare(
      "SELECT * FROM document_versions WHERE document_id = ? AND source = 'generated' ORDER BY version DESC LIMIT 1",
    )
    .get(documentId) as VersionRecord | undefined;
  if (!generated) throw new Error("No approved generated version to restore.");
  const buffer = fs.readFileSync(generated.file_path);
  return uploadDocument(documentId, buffer, actor, "restored", "Restored the last generated approved document.");
}

export async function verifyCurrent(documentId: string, actor = "human:operator", reason?: string) {
  const approved = approvedManifest(documentId);
  const version = currentVersion(documentId);
  if (!approved || !version) throw new Error("Nothing to verify.");
  const buffer = fs.readFileSync(version.file_path);
  const extracted = await extractFromBuffer(buffer);
  const semantic = await proposeSemanticFindings(approved.payload, extracted);
  const decision = decideGate(approved.payload, extracted, semantic.findings, semantic.used);

  db()
    .prepare("INSERT INTO extracted_terms (id, version_id, payload, created_at) VALUES (?, ?, ?, ?)")
    .run(nanoid(12), version.id, JSON.stringify(extracted), now());

  const decisionId = nanoid(12);
  db()
    .prepare(
      `INSERT INTO gate_decisions (id, document_id, version_id, manifest_id, status, payload, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
    )
    .run(decisionId, documentId, version.id, approved.id, decision.status, JSON.stringify(decision), now());

  const insertDisc = db().prepare(
    `INSERT INTO discrepancies (id, gate_decision_id, version_id, severity, layer, field, payload)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
  );
  for (const item of decision.discrepancies) {
    insertDisc.run(item.id, decisionId, version.id, item.severity, item.layer, item.field, JSON.stringify(item));
  }

  const previous = getDocument(documentId).status;
  const next: DocumentStatus = decision.status === "open" ? "verified_open" : "verified_blocked";
  setStatus(documentId, next);
  writeAudit({
    document_id: documentId,
    actor,
    document_hash: version.sha256,
    manifest_version: approved.version,
    action: "verify",
    previous_state: previous,
    new_state: next,
    reason: reason ?? "Final document compared against the approved Intent Manifest.",
    metadata: {
      gate: decision.status,
      critical: decision.critical_count,
      material: decision.material_count,
      llm_used: decision.llm_used,
    },
  });
  return getSession(documentId);
}

export async function requestSignature(
  documentId: string,
  actor = "human:operator",
  signerEmail?: string,
) {
  const session = getSession(documentId);
  if (!session.decision || session.decision.status !== "open") {
    throw new Error("SIGNATURE GATE: BLOCKED. The eSign API is not called until verification opens the gate.");
  }
  if (!session.approved_manifest || !session.current_version) {
    throw new Error("Missing approved manifest or document version.");
  }
  const gateRow = db()
    .prepare("SELECT id FROM gate_decisions WHERE document_id = ? ORDER BY created_at DESC LIMIT 1")
    .get(documentId) as { id: string };
  const email = signerEmail || session.approved_manifest.payload.signer.email;
  const name = session.approved_manifest.payload.signer.name;

  let provider: "foxit" | "simulated" = "simulated";
  let providerRef: string | null = `sim_${nanoid(8)}`;
  let raw: unknown = { simulated: true, message: "Human signing desk prepared. Agent cannot complete the signature." };

  if (foxitConfigured()) {
    try {
      const result = await foxitCreateEnvelope({
        folderName: session.document.title,
        signerEmail: email,
        signerName: name,
        base64Pdf: fs.readFileSync(session.current_version.file_path).toString("base64"),
      });
      provider = result.provider;
      providerRef = result.provider_ref;
      raw = result.raw;
    } catch (error) {
      raw = {
        simulated: true,
        foxit_error: error instanceof Error ? error.message : String(error),
        message: "Foxit eSign call failed; prepared a local human signing desk instead.",
      };
    }
  }

  const id = nanoid(12);
  db()
    .prepare(
      `INSERT INTO signature_requests
        (id, document_id, version_id, gate_decision_id, provider, provider_ref, signer_email, status, created_at, raw)
       VALUES (?, ?, ?, ?, ?, ?, ?, 'prepared', ?, ?)`,
    )
    .run(
      id,
      documentId,
      session.current_version.id,
      gateRow.id,
      provider,
      providerRef,
      email,
      now(),
      JSON.stringify(raw),
    );
  setStatus(documentId, "sent_for_signature");
  writeAudit({
    document_id: documentId,
    actor,
    document_hash: session.current_version.sha256,
    manifest_version: session.approved_manifest.version,
    action: "prepare_signature",
    previous_state: "verified_open",
    new_state: "sent_for_signature",
    reason: "Gate was open. Prepared a signature request for a human signer. The agent did not sign.",
    metadata: { provider, provider_ref: providerRef, signer_email: email },
  });
  return getSession(documentId);
}

export function completeHumanSignature(documentId: string, actor = "human:signer") {
  const request = latestSignature(documentId);
  if (!request) throw new Error("No signature request");
  const doc = getDocument(documentId);
  if (doc.status !== "sent_for_signature") {
    throw new Error("Signature handoff is not active.");
  }
  db().prepare("UPDATE signature_requests SET status = 'signed' WHERE id = ?").run(request.id);
  writeAudit({
    document_id: documentId,
    actor,
    document_hash: currentVersion(documentId)?.sha256 ?? null,
    manifest_version: approvedManifest(documentId)?.version ?? null,
    action: "human_sign",
    previous_state: "sent_for_signature",
    new_state: "sent_for_signature",
    reason: "A human completed the legally meaningful signing action.",
    metadata: { signature_request_id: request.id },
  });
  return getSession(documentId);
}

export function pdfPath(documentId: string) {
  const version = currentVersion(documentId);
  if (!version) throw new Error("No PDF yet");
  return version.file_path;
}

export async function buildReceipt(documentId: string) {
  const session = getSession(documentId);
  const findings = (session.decision?.discrepancies ?? []).map(
    (item) => `${item.severity.toUpperCase()} · ${item.title}: approved ${item.approved_value} / found ${item.found_value}`,
  );
  const pdf = await generateReceiptPdf({
    documentId,
    title: session.document.title,
    gate: session.decision?.status ?? "closed",
    checksum: session.decision?.semantic_checksum ?? "n/a",
    actor: session.document.actor,
    findings,
  });
  return {
    pdf,
    json: {
      document: session.document,
      approved_manifest: session.approved_manifest?.payload ?? null,
      semantic_checksum: session.decision?.semantic_checksum ?? null,
      gate: session.decision?.status ?? "closed",
      discrepancies: session.decision?.discrepancies ?? [],
      audit: session.audit,
      generated_at: now(),
    },
  };
}
