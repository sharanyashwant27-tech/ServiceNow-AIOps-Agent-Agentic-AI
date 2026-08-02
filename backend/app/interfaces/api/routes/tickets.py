from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dto.schemas import (
    AITicketCreateRequest,
    AgentRunResponse,
    CommentCreate,
    ResolutionWorkflowRequest,
    TicketCreate,
    TicketOut,
    TicketStateUpdate,
    WorkNoteCreate,
)
from app.application.use_cases.ticket_service import TicketService
from app.infrastructure.db.models import UserModel
from app.infrastructure.db.session import get_db
from app.interfaces.api.deps import get_current_user

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("", response_model=list[TicketOut])
async def list_tickets(
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_current_user),
) -> list[dict]:
    return await TicketService(db).list_tickets()


@router.post("/ai-draft")
async def ai_ticket_draft(
    body: AITicketCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_current_user),
) -> dict:
    """AI Ticket Creation — preview structured fields from free-text user input."""
    from sqlalchemy import select

    from app.agents.ai_ticket_creation import ai_ticket_creation_agent
    from app.infrastructure.db.models import EngineerModel

    engineers = list((await db.scalars(select(EngineerModel).where(EngineerModel.active.is_(True)))).all())
    eng_payload = [
        {
            "name": e.name,
            "email": e.email,
            "skills": e.skills,
            "assignment_group": e.assignment_group,
            "team": e.assignment_group,
            "active": e.active,
        }
        for e in engineers
    ]
    return ai_ticket_creation_agent.generate(body.user_text, eng_payload)


@router.post("", response_model=AgentRunResponse)
async def create_ticket(
    body: TicketCreate,
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_current_user),
) -> dict:
    title = body.resolved_title()
    description = body.description
    if body.use_ai_draft or not title:
        from sqlalchemy import select

        from app.agents.ai_ticket_creation import ai_ticket_creation_agent
        from app.infrastructure.db.models import EngineerModel

        source_text = description or title
        engineers = list((await db.scalars(select(EngineerModel).where(EngineerModel.active.is_(True)))).all())
        eng_payload = [
            {
                "name": e.name,
                "email": e.email,
                "skills": e.skills,
                "assignment_group": e.assignment_group,
                "team": e.assignment_group,
                "active": e.active,
            }
            for e in engineers
        ]
        ai = ai_ticket_creation_agent.generate(source_text, eng_payload)
        draft = ai.get("draft") or {}
        title = draft.get("title") or title or source_text[:80]
        # Keep original user words in description; AI fills structured fields via triage + metadata
        if not description:
            description = source_text
        result = await TicketService(db).create_and_triage(
            short_description=title,
            description=description,
            caller=body.resolved_created_by(),
            configuration_item=body.configuration_item,
            sync_servicenow=body.sync_servicenow,
            ai_draft=draft,
        )
        result["ai_ticket_creation"] = ai
        return result

    if not title:
        raise HTTPException(status_code=400, detail="title or short_description is required")
    result = await TicketService(db).create_and_triage(
        short_description=title,
        description=description,
        caller=body.resolved_created_by(),
        configuration_item=body.configuration_item,
        sync_servicenow=body.sync_servicenow,
    )
    return result


@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_current_user),
) -> dict:
    ticket = await TicketService(db).get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.get("/{ticket_id}/activity-notes")
async def get_activity_notes(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_current_user),
) -> dict:
    """Notes Viewer — Activity Notes for a ticket."""
    ticket = await TicketService(db).get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {
        "ticket_number": ticket["number"],
        "activity_notes": ticket["activity_notes"],
        "viewer": ticket["activity_notes_viewer"],
    }


@router.patch("/{ticket_id}/state", response_model=TicketOut)
async def update_state(
    ticket_id: str,
    body: TicketStateUpdate,
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_current_user),
) -> dict:
    try:
        ticket = await TicketService(db).update_state(ticket_id, body.state, body.actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.post("/{ticket_id}/resolution-workflow")
async def run_resolution_workflow(
    ticket_id: str,
    body: ResolutionWorkflowRequest,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_user),
) -> dict:
    """
    Resolution Workflow:
    Engineer → Resolve Ticket → AI Verify → Customer Email → Close Ticket → Store Embedding
    """
    from app.infrastructure.automation.resolution_workflow import resolution_workflow

    try:
        return await resolution_workflow.run(
            db,
            ticket_id=ticket_id,
            engineer=body.engineer or user.email,
            resolution_note=body.resolution_note,
            auto_close=body.auto_close,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{ticket_id}/work-notes", response_model=TicketOut)
async def add_work_note(
    ticket_id: str,
    body: WorkNoteCreate,
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_current_user),
) -> dict:
    ticket = await TicketService(db).add_work_note(
        ticket_id,
        body.author,
        body.body,
        body.is_internal,
        format=body.format,
        image_ids=body.image_ids,
        attachment_ids=body.attachment_ids,
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.post("/{ticket_id}/ai-summary", response_model=TicketOut)
async def refresh_ai_summary(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_current_user),
) -> dict:
    ticket = await TicketService(db).refresh_ai_summary(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.post("/{ticket_id}/comments", response_model=TicketOut)
async def add_comment(
    ticket_id: str,
    body: CommentCreate,
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_current_user),
) -> dict:
    ticket = await TicketService(db).add_comment(ticket_id, body.author, body.body)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.post("/{ticket_id}/attachments", response_model=TicketOut)
async def add_attachment(
    ticket_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_user),
) -> dict:
    import base64
    from datetime import datetime, timezone
    from uuid import uuid4

    from app.infrastructure.db.models import TicketModel
    from app.infrastructure.ocr.tesseract_ocr import tesseract_ocr
    from app.application.use_cases.ticket_service import _serialize_ticket

    ticket = await db.get(TicketModel, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    content = await file.read()
    max_bytes = 2_000_000
    if len(content) > max_bytes:
        raise HTTPException(status_code=400, detail=f"File too large (max {max_bytes} bytes)")

    content_type = file.content_type or "application/octet-stream"
    is_image = content_type.startswith("image/")
    ocr = tesseract_ocr.extract_text(content, filename=file.filename or "", content_type=content_type)
    att_id = str(uuid4())
    attachments = list(ticket.attachments or [])
    attachments.append(
        {
            "id": att_id,
            "filename": file.filename,
            "content_type": content_type,
            "size_bytes": len(content),
            "content_base64": base64.b64encode(content).decode("ascii"),
            "storage_path": f"memory://{ticket_id}/{file.filename}",
            "uploaded_by": user.email,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ocr": ocr,
        }
    )
    ticket.attachments = attachments

    # Activity note for Notes Viewer (Markdown + image/attachment link)
    md_body = f"**Attachment uploaded:** `{file.filename}` ({content_type})"
    if is_image:
        md_body += f"\n\n![{file.filename}](/api/v1/tickets/{ticket_id}/attachments/{att_id})"
    if ocr.get("text"):
        md_body += f"\n\n**OCR**\n\n```\n{ocr.get('text')[:1500]}\n```"

    notes = list(ticket.work_notes or [])
    notes.append(
        {
            "id": str(uuid4()),
            "author": user.email,
            "body": md_body,
            "format": "markdown",
            "image_ids": [att_id] if is_image else [],
            "attachment_ids": [att_id],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "is_internal": True,
        }
    )
    ticket.work_notes = notes
    await db.commit()
    await db.refresh(ticket)
    return _serialize_ticket(ticket)


@router.get("/{ticket_id}/attachments/{attachment_id}")
async def get_attachment(
    ticket_id: str,
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_current_user),
):
    import base64

    from fastapi.responses import Response

    from app.infrastructure.db.models import TicketModel

    ticket = await db.get(TicketModel, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    att = next((a for a in (ticket.attachments or []) if a.get("id") == attachment_id), None)
    if not att or not att.get("content_base64"):
        raise HTTPException(status_code=404, detail="Attachment not found")
    data = base64.b64decode(att["content_base64"])
    return Response(
        content=data,
        media_type=att.get("content_type") or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{att.get("filename") or "file"}"'},
    )
