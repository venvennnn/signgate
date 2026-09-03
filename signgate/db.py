from __future__ import annotations

import os
import sqlite3
from pathlib import Path

_CONN: sqlite3.Connection | None = None


def data_dir() -> Path:
    return Path(os.environ.get("SIGNGATE_DATA_DIR", Path.cwd() / "data"))


def files_dir() -> Path:
    path = data_dir() / "files"
    path.mkdir(parents=True, exist_ok=True)
    return path


def reset_connection() -> None:
    global _CONN
    if _CONN is not None:
        _CONN.close()
        _CONN = None


def connect() -> sqlite3.Connection:
    global _CONN
    if _CONN is not None:
        return _CONN
    data_dir().mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(data_dir() / "signgate.db", check_same_thread=False)
    _CONN = conn
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(
        """
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
        """
    )
    conn.commit()
    return conn
