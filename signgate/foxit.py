from __future__ import annotations

import os
import time
from typing import Any

import requests


def foxit_configured() -> bool:
    return bool(os.environ.get("FOXIT_CLIENT_ID") and os.environ.get("FOXIT_CLIENT_SECRET"))


def _host() -> str:
    return os.environ.get("FOXIT_API_HOST", "https://na1.fusion.foxit.com").rstrip("/")


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "client_id": os.environ.get("FOXIT_CLIENT_ID", ""),
        "client_secret": os.environ.get("FOXIT_CLIENT_SECRET", ""),
    }
    if extra:
        headers.update(extra)
    return headers


def _poll(task_id: str, timeout_s: int = 60) -> dict[str, Any]:
    started = time.time()
    while time.time() - started < timeout_s:
        res = requests.get(f"{_host()}/pdf-services/api/tasks/{task_id}", headers=_headers({"Content-Type": "application/json"}), timeout=30)
        res.raise_for_status()
        body = res.json()
        if body.get("status") == "COMPLETED":
            return body
        if body.get("status") == "FAILED":
            raise RuntimeError(f"Foxit task failed: {body}")
        time.sleep(1.5)
    raise TimeoutError("Foxit task timed out")


def _download(document_id: str) -> bytes:
    res = requests.get(f"{_host()}/pdf-services/api/documents/{document_id}/download", headers=_headers(), timeout=60)
    res.raise_for_status()
    return res.content


def _upload(filename: str, data: bytes, mime: str) -> str:
    res = requests.post(
        f"{_host()}/pdf-services/api/documents/upload",
        headers=_headers(),
        files={"file": (filename, data, mime)},
        timeout=60,
    )
    res.raise_for_status()
    return res.json()["documentId"]


def foxit_html_to_pdf(html: str) -> bytes:
    document_id = _upload("agreement.html", html.encode("utf-8"), "text/html")
    res = requests.post(
        f"{_host()}/pdf-services/api/documents/create/pdf-from-html",
        headers=_headers({"Content-Type": "application/json"}),
        json={"documentId": document_id},
        timeout=30,
    )
    res.raise_for_status()
    done = _poll(res.json()["taskId"])
    return _download(done["resultDocumentId"])


def foxit_pdf_to_text(pdf: bytes) -> str:
    document_id = _upload("document.pdf", pdf, "application/pdf")
    res = requests.post(
        f"{_host()}/pdf-services/api/documents/convert/pdf-to-text",
        headers=_headers({"Content-Type": "application/json"}),
        json={"documentId": document_id},
        timeout=30,
    )
    res.raise_for_status()
    done = _poll(res.json()["taskId"])
    return _download(done["resultDocumentId"]).decode("utf-8", errors="replace")


def foxit_create_envelope(folder_name: str, signer_email: str, signer_name: str, pdf: bytes) -> dict[str, Any]:
    parts = signer_name.split(" ", 1)
    first, last = parts[0], parts[1] if len(parts) > 1 else "Signer"
    body = {
        "folderName": folder_name,
        "inputType": "base64",
        "base64FileString": __import__("base64").b64encode(pdf).decode("ascii"),
        "fileNames": [f"{folder_name}.pdf"],
        "parties": [
            {
                "firstName": first,
                "lastName": last,
                "emailId": signer_email,
                "permission": "FILL_FIELDS_AND_SIGN",
                "sequence": 1,
            }
        ],
        "fields": [
            {
                "type": "signature",
                "x": 72,
                "y": 120,
                "width": 160,
                "height": 40,
                "documentNumber": 1,
                "pageNumber": 1,
                "party": 1,
                "required": True,
            }
        ],
        "processTextTags": False,
        "processAcroFields": False,
        "createEmbeddedSigningSession": True,
        "sendNow": True,
    }
    res = requests.post(
        f"{_host()}/esign/api/v1/folders/createfolder",
        headers=_headers({"Content-Type": "application/json"}),
        json=body,
        timeout=60,
    )
    res.raise_for_status()
    raw = res.json()
    return {
        "provider": "foxit",
        "provider_ref": raw.get("folderId") or (raw.get("folder") or {}).get("folderId") or raw.get("id"),
        "raw": raw,
    }
