from __future__ import annotations

import base64
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


def _poll(task_id: str, timeout_s: int = 90) -> dict[str, Any]:
    started = time.time()
    while time.time() - started < timeout_s:
        res = requests.get(
            f"{_host()}/pdf-services/api/tasks/{task_id}",
            headers=_headers({"Content-Type": "application/json"}),
            timeout=30,
        )
        res.raise_for_status()
        body = res.json()
        if body.get("status") == "COMPLETED":
            return body
        if body.get("status") == "FAILED":
            raise RuntimeError(f"Foxit task failed: {body}")
        time.sleep(1.5)
    raise TimeoutError("Foxit task timed out")


def _download(document_id: str) -> bytes:
    res = requests.get(
        f"{_host()}/pdf-services/api/documents/{document_id}/download",
        headers=_headers(),
        timeout=60,
    )
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


def foxit_ocr(pdf: bytes, languages: list[str] | None = None) -> bytes:
    """Turn a scanned PDF into a searchable PDF via Foxit OCR."""
    document_id = _upload("scan.pdf", pdf, "application/pdf")
    res = requests.post(
        f"{_host()}/pdf-services/api/documents/analyze/pdf-ocr",
        headers=_headers({"Content-Type": "application/json"}),
        json={
            "documentId": document_id,
            "config": {
                "languages": languages or ["en-US"],
                "makeEditable": True,
            },
        },
        timeout=30,
    )
    res.raise_for_status()
    done = _poll(res.json()["taskId"], timeout_s=120)
    return _download(done["resultDocumentId"])


def foxit_combine(pdfs: list[bytes]) -> bytes:
    """Merge PDFs in order (cover sheet first) via Foxit Combine."""
    if not pdfs:
        raise ValueError("Nothing to combine")
    if len(pdfs) == 1:
        return pdfs[0]
    infos = []
    for index, blob in enumerate(pdfs):
        infos.append({"documentId": _upload(f"part-{index}.pdf", blob, "application/pdf")})
    res = requests.post(
        f"{_host()}/pdf-services/api/documents/enhance/pdf-combine",
        headers=_headers({"Content-Type": "application/json"}),
        json={
            "documentInfos": infos,
            "config": {
                "addBookmark": False,
                "continueMergeOnError": False,
                "retainPageNumbers": False,
            },
        },
        timeout=30,
    )
    res.raise_for_status()
    done = _poll(res.json()["taskId"])
    return _download(done["resultDocumentId"])


def foxit_generate_document(template_docx: bytes, document_values: dict[str, Any], output_format: str = "pdf") -> bytes:
    """Foxit Document Generation: DOCX template + JSON values → PDF."""
    payload = {
        "base64FileString": base64.b64encode(template_docx).decode("ascii"),
        "documentValues": document_values,
        "outputFormat": output_format,
    }
    res = requests.post(
        f"{_host()}/document-generation/api/GenerateDocumentBase64",
        headers=_headers({"Content-Type": "application/json"}),
        json=payload,
        timeout=60,
    )
    res.raise_for_status()
    body = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
    encoded = None
    if isinstance(body, dict):
        encoded = (
            body.get("base64FileString")
            or body.get("documentBase64")
            or body.get("fileContent")
            or (body.get("data") or {}).get("base64FileString")
        )
    if encoded:
        return base64.b64decode(encoded)
    return res.content


def foxit_create_envelope(
    folder_name: str,
    signer_email: str,
    signer_name: str,
    pdf: bytes,
    page_number: int = 1,
) -> dict[str, Any]:
    parts = signer_name.split(" ", 1)
    first, last = parts[0], parts[1] if len(parts) > 1 else "Signer"
    body = {
        "folderName": folder_name,
        "inputType": "base64",
        "base64FileString": base64.b64encode(pdf).decode("ascii"),
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
                "pageNumber": max(1, page_number),
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
