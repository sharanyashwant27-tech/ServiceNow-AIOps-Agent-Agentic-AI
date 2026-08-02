"""AI Ticket Creation — turn free-text user input into a structured ticket draft."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.sub_agents import ClassificationAgent, PriorityAgent
from app.infrastructure.vector.qdrant_store import vector_store


@dataclass
class AITicketDraft:
    user_text: str
    title: str
    category: str
    subcategory: str
    priority: str
    assignment: str
    assigned_to: str | None
    sla: str
    suggested_resolution: str
    related_kb: str
    confidence: float
    details: dict[str, Any]


# Scenario playbooks for high-precision demos
SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "outlook_update",
        "match": lambda t: "outlook" in t
        and (
            "not opening" in t
            or "won't open" in t
            or "cant open" in t
            or "can't open" in t
            or "update" in t
        ),
        "title": "Outlook Application Failure",
        "category": "Software",
        "subcategory": "Email",
        "priority": "P2",
        "assignment": "Desktop Team",
        "sla": "4 Hours",
        "suggested_resolution": "Restart Outlook Cache",
        "related_kb": "KB-2025-889",
        "confidence": 0.96,
    },
    {
        "id": "vpn_down",
        "match": lambda t: "vpn" in t and ("not working" in t or "down" in t or "unable" in t),
        "title": "VPN Connectivity Failure",
        "category": "Network",
        "subcategory": "Network",
        "priority": "P2",
        "assignment": "Infrastructure",
        "sla": "4 Hours",
        "suggested_resolution": "Reset VPN client profile and validate gateway health",
        "related_kb": "KB-VPN-CONCENTRATOR",
        "confidence": 0.95,
    },
    {
        "id": "email_server_down",
        "match": lambda t: "email server" in t and "down" in t,
        "title": "Email Server Outage",
        "category": "Infrastructure",
        "subcategory": "Email",
        "priority": "P1",
        "assignment": "Infrastructure",
        "sla": "2 Hours",
        "suggested_resolution": "Failover EMAIL-GATEWAY and validate Storage-D",
        "related_kb": "KB-EMAIL-DOWN",
        "confidence": 0.97,
    },
]


class AITicketCreationAgent:
    """
    AI Ticket Creation

    User writes free text → AI generates:
      Title, Category, Priority, Assignment, SLA,
      Suggested Resolution, Related KB
    """

    def generate(self, user_text: str, engineers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        text = (user_text or "").strip()
        if not text:
            return {
                "user_text": "",
                "error": "user_text is required",
                "draft": None,
            }

        lower = text.lower()
        for scenario in SCENARIOS:
            if scenario["match"](lower):
                draft = self._from_scenario(text, scenario, engineers or [])
                return self._response(draft)

        return self._response(self._heuristic_draft(text, engineers or []))

    def _from_scenario(self, user_text: str, scenario: dict[str, Any], engineers: list[dict[str, Any]]) -> AITicketDraft:
        assignee = self._pick_team_member(scenario["assignment"], engineers)
        return AITicketDraft(
            user_text=user_text,
            title=scenario["title"],
            category=scenario["category"],
            subcategory=scenario.get("subcategory", scenario["category"]),
            priority=scenario["priority"],
            assignment=scenario["assignment"],
            assigned_to=assignee,
            sla=scenario["sla"],
            suggested_resolution=scenario["suggested_resolution"],
            related_kb=scenario["related_kb"],
            confidence=float(scenario["confidence"]),
            details={"scenario": scenario["id"], "source": "ai_ticket_creation_playbook"},
        )

    def _heuristic_draft(self, user_text: str, engineers: list[dict[str, Any]]) -> AITicketDraft:
        classification = ClassificationAgent().run(user_text, user_text)
        priority = PriorityAgent().run(user_text, user_text)
        sub = classification.data.get("subcategory") or "General"
        ticket_type = classification.data.get("ticket_type") or "Incident"

        # Map to IT service category for AI Ticket Creation UX
        category_map = {
            "Email": "Software",
            "Endpoint": "Software",
            "Application": "Software",
            "Network": "Network",
            "Database": "Database",
            "Infrastructure": "Infrastructure",
            "Security": "Security",
        }
        category = category_map.get(sub, "Software" if ticket_type == "Incident" else "Service Request")
        team_map = {
            "Software": "Desktop Team",
            "Email": "Desktop Team",
            "Endpoint": "Desktop Team",
            "Network": "Infrastructure",
            "Infrastructure": "Infrastructure",
            "Database": "DBA Team",
            "Security": "SecOps",
            "Application": "App Support",
        }
        assignment = team_map.get(category) or team_map.get(sub) or "IT Support"
        pri = priority.data.get("priority", "P3")
        sla = priority.data.get("resolution_time") or "6 Hours"

        title = self._title_from_text(user_text, category)
        kb_hits = vector_store.search(user_text, limit=3)
        related_kb = "KB-GENERAL"
        suggested = "Collect repro steps and apply standard remediation"
        if kb_hits:
            related_kb = kb_hits[0].payload.get("kb_id") or kb_hits[0].payload.get("title") or related_kb
            snippet = (kb_hits[0].payload.get("content") or "")[:160]
            if snippet:
                suggested = snippet.split(".")[0].strip() or suggested

        if "outlook" in user_text.lower():
            title = "Outlook Application Failure"
            category = "Software"
            assignment = "Desktop Team"
            pri = "P2"
            sla = "4 Hours"
            suggested = "Restart Outlook Cache"
            related_kb = "KB-2025-889"

        return AITicketDraft(
            user_text=user_text,
            title=title,
            category=category,
            subcategory=sub,
            priority=pri,
            assignment=assignment,
            assigned_to=self._pick_team_member(assignment, engineers),
            sla=sla,
            suggested_resolution=suggested,
            related_kb=str(related_kb),
            confidence=round(
                min(
                    0.94,
                    0.55
                    + 0.25 * float(classification.confidence)
                    + 0.2 * float(priority.confidence),
                ),
                4,
            ),
            details={"scenario": "heuristic", "source": "ai_ticket_creation"},
        )

    def _title_from_text(self, text: str, category: str) -> str:
        cleaned = " ".join(text.strip().rstrip(".").split())
        if len(cleaned) <= 60:
            # Elevate to a concise incident-style title
            words = cleaned.split()
            if len(words) <= 8:
                return cleaned.title() if cleaned.islower() else cleaned
        # Fallback: Category + first meaningful phrase
        phrase = cleaned.split(".")[0][:48].rstrip()
        return f"{category} Issue — {phrase}"

    def _pick_team_member(self, team: str, engineers: list[dict[str, Any]]) -> str | None:
        team_l = (team or "").lower()
        for eng in engineers:
            group = (eng.get("assignment_group") or eng.get("team") or "").lower()
            if team_l and team_l in group:
                return eng.get("email")
        # Desktop Team soft match on endpoint/software skills
        if "desktop" in team_l:
            for eng in engineers:
                skills = [s.lower() for s in eng.get("skills") or []]
                if any(k in skills for k in ("outlook", "desktop", "endpoint", "software", "windows")):
                    return eng.get("email")
        return engineers[0]["email"] if engineers else None

    def _response(self, draft: AITicketDraft) -> dict[str, Any]:
        return {
            "feature": "AI Ticket Creation",
            "user_text": draft.user_text,
            "draft": {
                "title": draft.title,
                "category": draft.category,
                "subcategory": draft.subcategory,
                "priority": draft.priority,
                "assignment": draft.assignment,
                "assigned_to": draft.assigned_to,
                "sla": draft.sla,
                "suggested_resolution": draft.suggested_resolution,
                "related_kb": draft.related_kb,
                "confidence": draft.confidence,
            },
            # Flattened view matching product copy
            "generated": {
                "Title": draft.title,
                "Category": draft.category,
                "Priority": draft.priority,
                "Assignment": draft.assignment,
                "SLA": draft.sla,
                "Suggested Resolution": draft.suggested_resolution,
                "Related KB": draft.related_kb,
            },
            "details": draft.details,
        }


ai_ticket_creation_agent = AITicketCreationAgent()
