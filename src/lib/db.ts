import Database from "better-sqlite3";
import fs from "node:fs";
import path from "node:path";

const DATA_DIR = path.join(process.cwd(), "data");
const FILES_DIR = path.join(DATA_DIR, "files");

export function filesDir() {
  fs.mkdirSync(FILES_DIR, { recursive: true });
  return FILES_DIR;
}

let singleton: Database.Database | null = null;

export function db() {
  if (singleton) return singleton;
  fs.mkdirSync(DATA_DIR, { recursive: true });
  const instance = new Database(path.join(DATA_DIR, "signgate.db"));
  instance.pragma("journal_mode = WAL");
  instance.exec(`
    CREATE TABLE IF NOT EXISTS documents (
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      document_type TEXT NOT NULL,
      status TEXT NOT NULL,
      prompt TEXT NOT NULL,
      actor TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS intent_manifests (
      id TEXT PRIMARY KEY,
      document_id TEXT NOT NULL,
      version INTEGER NOT NULL,
      payload TEXT NOT NULL,
      status TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS manifest_approvals (
      id TEXT PRIMARY KEY,
      manifest_id TEXT NOT NULL,
      actor TEXT NOT NULL,
      approved_at TEXT NOT NULL,
      notes TEXT
    );
    CREATE TABLE IF NOT EXISTS document_versions (
      id TEXT PRIMARY KEY,
      document_id TEXT NOT NULL,
      version INTEGER NOT NULL,
      source TEXT NOT NULL,
      file_path TEXT NOT NULL,
      sha256 TEXT NOT NULL,
      page_count INTEGER NOT NULL,
      created_at TEXT NOT NULL,
      is_current INTEGER NOT NULL,
      notes TEXT
    );
    CREATE TABLE IF NOT EXISTS extracted_terms (
      id TEXT PRIMARY KEY,
      version_id TEXT NOT NULL,
      payload TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS gate_decisions (
      id TEXT PRIMARY KEY,
      document_id TEXT NOT NULL,
      version_id TEXT NOT NULL,
      manifest_id TEXT NOT NULL,
      status TEXT NOT NULL,
      payload TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS discrepancies (
      id TEXT PRIMARY KEY,
      gate_decision_id TEXT NOT NULL,
      version_id TEXT NOT NULL,
      severity TEXT NOT NULL,
      layer TEXT NOT NULL,
      field TEXT NOT NULL,
      payload TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS signature_requests (
      id TEXT PRIMARY KEY,
      document_id TEXT NOT NULL,
      version_id TEXT NOT NULL,
      gate_decision_id TEXT NOT NULL,
      provider TEXT NOT NULL,
      provider_ref TEXT,
      signer_email TEXT NOT NULL,
      status TEXT NOT NULL,
      created_at TEXT NOT NULL,
      raw TEXT
    );
    CREATE TABLE IF NOT EXISTS audit_events (
      id TEXT PRIMARY KEY,
      document_id TEXT NOT NULL,
      actor TEXT NOT NULL,
      timestamp TEXT NOT NULL,
      document_hash TEXT,
      manifest_version INTEGER,
      action TEXT NOT NULL,
      previous_state TEXT,
      new_state TEXT,
      reason TEXT,
      metadata TEXT
    );
  `);
  singleton = instance;
  return instance;
}
