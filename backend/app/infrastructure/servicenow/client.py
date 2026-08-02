from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ServiceNowClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.servicenow_instance_url and self.settings.servicenow_username)

    async def create_incident(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return {"mocked": True, "sys_id": "local", "number": payload.get("number"), "payload": payload}
        url = f"{self.settings.servicenow_instance_url.rstrip('/')}/api/now/table/incident"
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                url,
                json={
                    "short_description": payload.get("short_description"),
                    "description": payload.get("description"),
                    "urgency": {"P1": "1", "P2": "2", "P3": "3"}.get(payload.get("priority", "P3"), "3"),
                    "category": payload.get("category"),
                    "assignment_group": payload.get("assignment_group"),
                    "assigned_to": payload.get("assigned_to"),
                },
                auth=(self.settings.servicenow_username, self.settings.servicenow_password),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_incident(self, number: str) -> dict[str, Any]:
        if not self.enabled:
            return {"mocked": True, "number": number}
        url = f"{self.settings.servicenow_instance_url.rstrip('/')}/api/now/table/incident"
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                url,
                params={"sysparm_query": f"number={number}", "sysparm_limit": 1},
                auth=(self.settings.servicenow_username, self.settings.servicenow_password),
            )
            resp.raise_for_status()
            return resp.json()


servicenow_client = ServiceNowClient()
