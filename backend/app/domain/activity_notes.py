"""Activity Notes model and Notes Viewer formatting for every ticket."""

from __future__ import annotations

from datetime import datetime
from typing import Any

NOTES_VIEWER_SUPPORTS = [
    {"id": "markdown", "title": "Markdown", "description": "Headings, lists, bold, links, code, and images in notes"},
    {"id": "images", "title": "Images", "description": "Inline image previews from uploaded image attachments"},
    {"id": "attachments", "title": "Attachments", "description": "Files linked to the ticket with download/OCR"},
    {"id": "ai_summary", "title": "AI Summary", "description": "Master Agent summary of the ticket and activity"},
]


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _date_label(value: Any) -> str:
    dt = _parse_dt(value)
    if not dt:
        return datetime.utcnow().strftime("%Y-%m-%d")
    return dt.strftime("%Y-%m-%d")


def normalize_activity_notes(work_notes: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Every ticket exposes Activity Notes derived from work notes (chronological)."""
    notes: list[dict[str, Any]] = []
    for note in work_notes or []:
        body = (note.get("body") or "").strip()
        if not body:
            continue
        notes.append(
            {
                "id": note.get("id"),
                "date": _date_label(note.get("created_at")),
                "text": body,
                "format": note.get("format") or "markdown",
                "author": note.get("author") or "system",
                "created_at": note.get("created_at"),
                "is_internal": bool(note.get("is_internal", True)),
                "image_ids": note.get("image_ids") or [],
                "attachment_ids": note.get("attachment_ids") or [],
            }
        )
    notes.sort(key=lambda n: (n.get("created_at") or "", n.get("date") or ""))
    return notes


def format_activity_notes_viewer(activity_notes: list[dict[str, Any]]) -> str:
    """
    Notes Viewer text format:

    2026-05-10

    Investigated VPN

    -------------------

    2026-05-10

    Restarted VPN Gateway
    """
    if not activity_notes:
        return "No activity notes yet."

    blocks: list[str] = []
    for note in activity_notes:
        blocks.append(f"{note['date']}\n\n{note['text']}")
    return "\n\n-------------------\n\n".join(blocks)


def public_attachment(att: dict[str, Any], ticket_id: str) -> dict[str, Any]:
    """Serialize attachment metadata for API (omit large binary unless image preview)."""
    content_type = att.get("content_type") or "application/octet-stream"
    is_image = str(content_type).startswith("image/")
    out = {
        "id": att.get("id"),
        "filename": att.get("filename"),
        "content_type": content_type,
        "size_bytes": att.get("size_bytes"),
        "uploaded_by": att.get("uploaded_by"),
        "created_at": att.get("created_at"),
        "date": _date_label(att.get("created_at")),
        "is_image": is_image,
        "has_content": bool(att.get("content_base64")),
        "download_url": f"/api/v1/tickets/{ticket_id}/attachments/{att.get('id')}",
        "ocr": att.get("ocr"),
    }
    # Small images get inline preview data URL for the Notes Viewer
    raw_b64 = att.get("content_base64")
    if is_image and raw_b64 and int(att.get("size_bytes") or 0) <= 1_500_000:
        out["preview_data_url"] = f"data:{content_type};base64,{raw_b64}"
    return out
