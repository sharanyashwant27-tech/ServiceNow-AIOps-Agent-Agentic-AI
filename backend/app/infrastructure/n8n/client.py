from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class N8NClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def trigger_workflow(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Trigger n8n. For ticket.created, execute the canonical in-process workflow
        (Webhook → Classification → Priority → Assignment → ServiceNow → Email → Slack → Log)
        and optionally forward to an external n8n webhook.
        """
        if event == "ticket.created":
            from app.infrastructure.n8n.ticket_created_workflow import ticket_created_n8n_workflow

            return await ticket_created_n8n_workflow.run(
                payload,
                engineers=payload.get("engineers"),
                sync_servicenow=payload.get("sync_servicenow", True),
            )
        return await self.forward_webhook({"event": event, "data": payload})

    async def forward_webhook(self, body: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.n8n_webhook_url:
            logger.info("n8n webhook not configured; event=%s", body.get("event"))
            return {"mocked": True, "forwarded": False, "event": body.get("event")}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(self.settings.n8n_webhook_url, json=body)
                return {
                    "mocked": False,
                    "forwarded": True,
                    "status_code": resp.status_code,
                    "body": resp.text[:500],
                }
        except Exception as exc:  # noqa: BLE001
            logger.warning("n8n forward failed: %s", exc)
            return {"mocked": False, "forwarded": False, "error": str(exc)}


n8n_client = N8NClient()
