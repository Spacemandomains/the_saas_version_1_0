from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

import requests
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

_connection_settings: Optional[Dict[str, Any]] = None
_settings_fetched_at: float = 0


def _get_access_token() -> str:
    global _connection_settings, _settings_fetched_at

    if (
        _connection_settings
        and _connection_settings.get("settings", {}).get("expires_at")
        and time.time() * 1000 < _parse_expiry(_connection_settings["settings"]["expires_at"])
    ):
        return _connection_settings["settings"]["access_token"]

    hostname = os.getenv("REPLIT_CONNECTORS_HOSTNAME")
    repl_identity = os.getenv("REPL_IDENTITY")
    web_repl_renewal = os.getenv("WEB_REPL_RENEWAL")

    if repl_identity:
        x_replit_token = "repl " + repl_identity
    elif web_repl_renewal:
        x_replit_token = "depl " + web_repl_renewal
    else:
        raise RuntimeError("Replit connector token not found")

    if not hostname:
        raise RuntimeError("REPLIT_CONNECTORS_HOSTNAME not set")

    resp = requests.get(
        f"https://{hostname}/api/v2/connection?include_secrets=true&connector_names=google-docs",
        headers={
            "Accept": "application/json",
            "X_REPLIT_TOKEN": x_replit_token,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    items = data.get("items", [])
    if not items:
        raise RuntimeError("Google Docs not connected. Please set up the Google Docs integration.")

    _connection_settings = items[0]
    _settings_fetched_at = time.time()

    settings = _connection_settings.get("settings", {})
    access_token = settings.get("access_token") or (
        settings.get("oauth", {}).get("credentials", {}).get("access_token")
    )

    if not access_token:
        raise RuntimeError("Google Docs access token not found")

    return access_token


def _parse_expiry(expires_at: Any) -> float:
    if isinstance(expires_at, (int, float)):
        return float(expires_at)
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        return dt.timestamp() * 1000
    except Exception:
        return 0


def _get_docs_service():
    access_token = _get_access_token()
    creds = Credentials(token=access_token)
    return build("docs", "v1", credentials=creds, cache_discovery=False)


def create_document(title: str) -> Dict[str, str]:
    service = _get_docs_service()
    doc = service.documents().create(body={"title": title}).execute()
    doc_id = doc.get("documentId")
    return {
        "document_id": doc_id,
        "url": f"https://docs.google.com/document/d/{doc_id}/edit",
        "title": title,
    }


def write_to_document(document_id: str, content: str) -> None:
    service = _get_docs_service()
    requests_body = [
        {
            "insertText": {
                "location": {"index": 1},
                "text": content,
            }
        }
    ]
    service.documents().batchUpdate(
        documentId=document_id,
        body={"requests": requests_body},
    ).execute()


def append_to_document(document_id: str, content: str) -> Dict[str, str]:
    service = _get_docs_service()
    doc = service.documents().get(documentId=document_id).execute()
    body_content = doc.get("body", {}).get("content", [])
    end_index = 1
    for element in body_content:
        ei = element.get("endIndex", 1)
        if ei > end_index:
            end_index = ei

    insert_index = max(end_index - 1, 1)
    separator = "\n\n" + "—" * 40 + "\n\n" if end_index > 2 else ""
    text_to_insert = separator + content

    reqs = [
        {
            "insertText": {
                "location": {"index": insert_index},
                "text": text_to_insert,
            }
        }
    ]
    service.documents().batchUpdate(
        documentId=document_id,
        body={"requests": reqs},
    ).execute()

    title = doc.get("title", "")
    return {
        "document_id": document_id,
        "url": f"https://docs.google.com/document/d/{document_id}/edit",
        "title": title,
    }


def read_document(document_id: str) -> Dict[str, Any]:
    service = _get_docs_service()
    doc = service.documents().get(documentId=document_id).execute()
    body_content = doc.get("body", {}).get("content", [])
    text_parts = []
    for element in body_content:
        paragraph = element.get("paragraph")
        if paragraph:
            for elem in paragraph.get("elements", []):
                text_run = elem.get("textRun")
                if text_run:
                    text_parts.append(text_run.get("content", ""))
    return {
        "document_id": document_id,
        "title": doc.get("title", ""),
        "text": "".join(text_parts),
    }


def create_and_write(title: str, content: str) -> Dict[str, str]:
    result = create_document(title)
    write_to_document(result["document_id"], content)
    return result


def format_doc_content(doc_type: str, title: str, output: Dict[str, Any]) -> str:
    lines = [f"{title}\n", f"Document Type: {doc_type.upper()}\n", "=" * 50 + "\n\n"]

    def _render(obj: Any, indent: int = 0) -> None:
        prefix = "  " * indent
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.startswith("_"):
                    continue
                label = k.replace("_", " ").title()
                if isinstance(v, (dict, list)):
                    lines.append(f"{prefix}{label}:\n")
                    _render(v, indent + 1)
                else:
                    lines.append(f"{prefix}{label}: {v}\n")
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, (dict, list)):
                    _render(item, indent)
                    lines.append("\n")
                else:
                    lines.append(f"{prefix}- {item}\n")
        else:
            lines.append(f"{prefix}{obj}\n")

    _render(output)
    return "".join(lines)
