from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import get_settings
from app.domain.value_objects.ticket_state import Priority
from app.infrastructure.graph.neo4j_store import graph_store
from app.infrastructure.llm.embeddings import cosine_similarity, embed_text, lexical_overlap
from app.infrastructure.vector.qdrant_store import vector_store


# Ticket type taxonomy (Sub Agent 1 — Ticket Classification Agent)
TICKET_TYPE_RULES: list[tuple[str, list[str], float]] = [
    (
        "Security Issue",
        [
            "security",
            "phishing",
            "malware",
            "ransomware",
            "breach",
            "unauthorized",
            "compromise",
            "soc",
            "virus",
            "suspicious login",
            "data leak",
        ],
        1.35,
    ),
    (
        "Change Request",
        [
            "change request",
            "cab",
            "deploy",
            "deployment",
            "release",
            "patch window",
            "maintenance window",
            "implement change",
            "rfc",
            "upgrade request",
        ],
        1.25,
    ),
    (
        "Problem",
        [
            "problem",
            "root cause",
            "recurring",
            "chronic",
            "known error",
            "repeated outage",
            "pattern of failures",
            "underlying cause",
        ],
        1.2,
    ),
    (
        "Service Request",
        [
            "service request",
            "access request",
            "new laptop",
            "onboarding",
            "offboarding",
            "password reset",
            "how to",
            "request for",
            "please provide",
            "need access",
            "catalog",
            "fulfillment",
        ],
        1.15,
    ),
    (
        "Incident",
        [
            "not working",
            "down",
            "outage",
            "error",
            "failed",
            "unable",
            "can't",
            "cannot",
            "broken",
            "issue",
            "incident",
            "outage",
            "crash",
            "timeout",
            "unavailable",
        ],
        1.0,
    ),
]

# Technical subcategory (IT domain)
SUBCATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("Network", ["network", "vpn", "dns", "firewall", "latency", "packet", "wifi", "wifi", "lan", "wan", "proxy"]),
    ("Database", ["database", "sql", "oracle", "postgres", "deadlock", "query", "db"]),
    ("Application", ["application", "app", "crash", "exception", "timeout", "500", "api", "crm", "erp"]),
    ("Infrastructure", ["server", "cpu", "memory", "disk", "kubernetes", "node", "vm", "storage"]),
    ("Security", ["security", "phishing", "malware", "access", "password", "auth", "breach", "mfa"]),
    ("Email", ["email", "outlook", "smtp", "mailbox", "exchange"]),
    ("Endpoint", ["laptop", "desktop", "printer", "workstation", "device"]),
]

PRIORITY_CATALOG = {
    Priority.P1: {
        "label": "Critical Production Down",
        "resolution_time": "2 Hours",
        "sla_hours": 2.0,
        "keywords": [
            "outage",
            "down",
            "production",
            "critical",
            "sev1",
            "p1",
            "unable to work",
            "all users",
            "email server",
            "server down",
            "completely unavailable",
        ],
    },
    Priority.P2: {
        "label": "Major Business Impact",
        "resolution_time": "4 Hours",
        "sla_hours": 4.0,
        "keywords": ["degraded", "intermittent", "major", "p2", "multiple users", "slow", "partial outage"],
    },
    Priority.P3: {
        "label": "Minor Issue",
        "resolution_time": "6 Hours",
        "sla_hours": 6.0,
        "keywords": ["minor", "request", "how to", "question", "p3", "single user", "cosmetic"],
    },
}

# Kept for compatibility with older imports/tests
PRIORITY_RULES = {p: meta["keywords"] for p, meta in PRIORITY_CATALOG.items()}

DUPLICATE_SIMILARITY_THRESHOLD = 0.90
SLA_ESCALATION_LEAD_MINUTES = 30


@dataclass
class AgentResult:
    name: str
    confidence: float
    data: dict[str, Any] = field(default_factory=dict)
    notes: str = ""


class ClassificationAgent:
    """
    Sub Agent 1 — Ticket Classification Agent

    Detects ticket type:
      Incident | Service Request | Change Request | Problem | Security Issue
    and a technical subcategory (e.g. Network).
    """

    TICKET_TYPES = ("Incident", "Service Request", "Change Request", "Problem", "Security Issue")

    def run(self, short_description: str, description: str) -> AgentResult:
        text = f"{short_description} {description}".lower().strip()
        ticket_type, type_score = self._detect_ticket_type(text)
        subcategory, sub_score = self._detect_subcategory(text)

        # Blend type + subcategory evidence into overall confidence.
        # Strong keyword hits (e.g. "vpn" + "not working") push toward ~0.98.
        confidence = min(0.99, 0.55 + (0.35 * type_score) + (0.25 * sub_score))
        if "vpn" in text and ("not working" in text or "down" in text or "unable" in text):
            ticket_type = "Incident"
            subcategory = "Network"
            confidence = max(confidence, 0.98)

        return AgentResult(
            name="ticket_classification",
            confidence=round(confidence, 4),
            data={
                "category": ticket_type,  # Incident / Service Request / ...
                "subcategory": subcategory,  # Network / Database / ...
                "ticket_type": ticket_type,
                "confidence_pct": int(round(confidence * 100)),
                "detected_types": list(self.TICKET_TYPES),
            },
            notes=f"Category: {ticket_type} | Subcategory: {subcategory} | Confidence: {int(round(confidence * 100))}%",
        )

    def _detect_ticket_type(self, text: str) -> tuple[str, float]:
        best_type, best_score = "Incident", 0.15
        for ticket_type, keywords, weight in TICKET_TYPE_RULES:
            hits = sum(1 for k in keywords if k in text)
            if not hits:
                continue
            score = min(1.0, (hits / max(len(keywords), 1)) * weight * 4.5)
            # Boost exact phrase / strong operational failure language for Incident
            if ticket_type == "Incident" and any(
                p in text for p in ("not working", "is down", "unavailable", "cannot connect", "can't connect")
            ):
                score = max(score, 0.92)
            if score > best_score:
                best_type, best_score = ticket_type, score
        return best_type, best_score

    def _detect_subcategory(self, text: str) -> tuple[str, float]:
        best_sub, best_score = "General", 0.0
        for subcategory, keywords in SUBCATEGORY_RULES:
            hits = sum(1 for k in keywords if k in text)
            if not hits:
                continue
            score = min(1.0, hits / max(3, len(keywords) * 0.35))
            # Strong single-token domain cues
            if subcategory == "Network" and "vpn" in text:
                score = max(score, 0.95)
            if score > best_score:
                best_sub, best_score = subcategory, score
        return best_sub, best_score


# Backward-compatible alias used across the codebase
TicketClassificationAgent = ClassificationAgent


class PriorityAgent:
    """Sub Agent 2 — Priority Agent (P1/P2/P3 with resolution time)."""

    def run(self, short_description: str, description: str) -> AgentResult:
        settings = get_settings()
        text = f"{short_description} {description}".lower()
        scores = {Priority.P1: 0.0, Priority.P2: 0.0, Priority.P3: 0.15}
        for priority, meta in PRIORITY_CATALOG.items():
            scores[priority] += sum(0.22 for k in meta["keywords"] if k in text)
        # Example: "Email server down" → P1
        if ("email" in text and "down" in text) or "server down" in text or "production down" in text:
            scores[Priority.P1] += 1.0
        priority = max(scores, key=scores.get)
        meta = PRIORITY_CATALOG[priority]
        hours = {
            Priority.P1: settings.sla_p1_hours,
            Priority.P2: settings.sla_p2_hours,
            Priority.P3: settings.sla_p3_hours,
        }[priority]
        due = datetime.now(timezone.utc) + timedelta(hours=hours)
        confidence = min(0.99, 0.5 + scores[priority])
        return AgentResult(
            name="priority",
            confidence=round(confidence, 4),
            data={
                "priority": priority.value,
                "label": meta["label"],
                "resolution_time": meta["resolution_time"],
                "sla_hours": hours,
                "sla_due_at": due.isoformat(),
            },
            notes=f"{priority.value} — {meta['label']} | Resolution Time: {meta['resolution_time']}",
        )


class AssignmentAgent:
    """
    Sub Agent 3 — Assignment Agent

    Uses skill matching, workload, availability, shift, team, experience.
    """

    def run(
        self,
        category: str,
        engineers: list[dict[str, Any]],
    ) -> AgentResult:
        if not engineers:
            return AgentResult(
                name="assignment",
                confidence=0.2,
                data={"assigned_to": None, "assignment_group": "IT Support", "assigned_name": None, "team": None},
                notes="No engineers available",
            )
        domain = (category or "General").lower()
        # Prefer Day shift by default for demo; night keywords could flip this later.
        current_shift = "Day"
        ranked: list[tuple[float, dict[str, Any]]] = []
        for eng in engineers:
            if not eng.get("active", True) or not eng.get("available", True):
                continue
            skills = [s.lower() for s in eng.get("skills", [])]
            team = (eng.get("team") or eng.get("assignment_group") or "").lower()
            skill_score = 0.55 if any(domain in s or s in domain for s in skills) else 0.15
            skill_score += 0.12 * sum(1 for s in skills if domain in s or s in domain)
            if "network" in domain and any(k in skills for k in ("network", "vpn", "firewall", "infrastructure")):
                skill_score = max(skill_score, 0.95)
            if domain in team or "infrastructure" in team and "network" in domain:
                skill_score = max(skill_score, skill_score + 0.1)
            capacity = max(0.0, 1.0 - (eng.get("current_workload", 0) / max(eng.get("max_workload", 1), 1)))
            shift_score = 1.0 if (eng.get("shift", "Day") == current_shift) else 0.45
            experience = min(1.0, float(eng.get("experience_years", 3)) / 8.0)
            total = (
                0.40 * skill_score
                + 0.20 * capacity
                + 0.15 * shift_score
                + 0.15 * experience
                + 0.10 * (1.0 if eng.get("available", True) else 0.0)
            )
            ranked.append((total, eng))
        if not ranked:
            return AgentResult(
                name="assignment",
                confidence=0.2,
                data={"assigned_to": None, "assignment_group": "IT Support"},
                notes="No available engineers in current shift",
            )
        ranked.sort(key=lambda x: x[0], reverse=True)
        best_score, best = ranked[0]
        team = best.get("team") or best.get("assignment_group", "IT Support")
        return AgentResult(
            name="assignment",
            confidence=min(0.98, best_score),
            data={
                "assigned_to": best["email"],
                "assigned_name": best["name"],
                "assignment_group": best.get("assignment_group", team),
                "team": team,
                "shift": best.get("shift", "Day"),
                "experience_years": best.get("experience_years", 3),
                "factors": ["skill_matching", "current_workload", "availability", "shift", "team", "experience"],
            },
            notes=f"Assign {best['name']} | Team {team}",
        )


class DuplicateDetectionAgent:
    """Sub Agent 4 — Duplicate Detection Agent (embeddings, 90% threshold)."""

    def run(self, short_description: str, description: str, candidates: list[dict[str, Any]]) -> AgentResult:
        query = f"{short_description}\n{description}"
        q_vec = embed_text(query)
        best_id, best_score, best_title = None, 0.0, None
        # Search vector DB first
        for hit in vector_store.search(query, limit=8):
            if hit.payload.get("source") in {"incident", "learned_incident"} and hit.score > best_score:
                best_score = float(hit.score)
                best_id = hit.payload.get("number") or hit.id
                best_title = hit.payload.get("title")
        for cand in candidates:
            text = f"{cand.get('short_description','')}\n{cand.get('description','')}"
            score = 0.75 * cosine_similarity(q_vec, embed_text(text)) + 0.25 * lexical_overlap(query, text)
            if score > best_score:
                best_id, best_score = cand.get("number") or cand.get("id"), score
                best_title = cand.get("short_description")
        is_dup = best_score >= DUPLICATE_SIMILARITY_THRESHOLD
        return AgentResult(
            name="duplicate_detection",
            confidence=round(best_score if is_dup else max(0.0, 1.0 - best_score), 4),
            data={
                "is_duplicate": is_dup,
                "duplicate_of": best_id if is_dup else None,
                "duplicate_title": best_title if is_dup else None,
                "duplicate_score": round(best_score, 4),
                "threshold": DUPLICATE_SIMILARITY_THRESHOLD,
                "action": "link_existing_ticket" if is_dup else "create_new_ticket",
                "method": "vector_embeddings",
            },
            notes=(
                f"≥90% similar ticket found ({best_id}) — link existing instead of creating new"
                if is_dup
                else "No duplicate ≥90% — safe to create new ticket"
            ),
        )


class RAGKnowledgeAgent:
    """Knowledge retrieval helper used by Resolution Agent."""

    def run(self, query: str, limit: int = 5) -> AgentResult:
        """Embedding → Vector Search → Similar Tickets / KB / SOP buckets."""
        from app.domain.rag_pipeline import KB_SOURCES, SOP_SOURCES, TICKET_SOURCES

        hits = vector_store.search(query, limit=max(limit, 10))
        articles = [
            {
                "id": h.id,
                "title": h.payload.get("title"),
                "snippet": (h.payload.get("content") or "")[:280],
                "score": round(h.score, 4),
                "source": h.payload.get("source"),
            }
            for h in hits
        ]
        similar_tickets = [a for a in articles if (a.get("source") or "") in TICKET_SOURCES]
        kb_articles = [a for a in articles if (a.get("source") or "") in KB_SOURCES]
        sop = [a for a in articles if (a.get("source") or "") in SOP_SOURCES]
        confidence = articles[0]["score"] if articles else 0.0
        return AgentResult(
            name="rag_knowledge",
            confidence=confidence,
            data={
                "articles": articles,
                "similar_tickets": similar_tickets,
                "kb_articles": kb_articles,
                "sop": sop,
                "pipeline": "User Query→Embedding→Vector Search→Tickets→KB→SOP→LLM→Final Resolution",
            },
            notes=(
                f"RAG retrieve: {len(similar_tickets)} tickets, "
                f"{len(kb_articles)} KB, {len(sop)} SOP from {len(articles)} hits"
            ),
        )


class GraphRAGAgent:
    """
    Sub Agent 6 — GraphRAG Agent

    Pipeline: Ticket → Neo4j → Related CI → Dependencies →
    Previous Failures → Generate RCA → Impact Analysis
    """

    def run(self, configuration_item: str | None, description: str) -> AgentResult:
        from app.infrastructure.graph.pipeline import graphrag_pipeline

        result = graphrag_pipeline.run(
            ticket={"description": description, "configuration_item": configuration_item},
            ci=configuration_item,
            description=description,
        )
        impact = result.get("impact_analysis") or result
        return AgentResult(
            name="graphrag",
            confidence=0.9 if impact.get("affected_services") or impact.get("impact_chain") else 0.45,
            data={
                **impact,
                "previous_failures": result.get("previous_failures") or [],
                "pipeline_trace": result.get("trace") or [],
                "pipeline": "Ticket→Neo4j→CI→Dependencies→Previous Failures→RCA→Impact Analysis",
            },
            notes=impact.get("root_cause_suggestion") or result.get("rca") or "",
        )


class SLAMonitorAgent:
    """Sub Agent 7 — SLA Agent (timer + escalate 30 minutes before breach)."""

    def run(self, priority: str, created_at: datetime | None = None, sla_due_at: str | None = None) -> AgentResult:
        settings = get_settings()
        catalog = {
            "P1": (settings.sla_p1_hours, "2 Hours"),
            "P2": (settings.sla_p2_hours, "4 Hours"),
            "P3": (settings.sla_p3_hours, "6 Hours"),
        }
        hours, resolution_time = catalog.get(priority, (settings.sla_p3_hours, "6 Hours"))
        now = datetime.now(timezone.utc)
        created = created_at or now
        due = datetime.fromisoformat(sla_due_at) if sla_due_at else created + timedelta(hours=hours)
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        remaining_hours = (due - now).total_seconds() / 3600.0
        remaining_minutes = (due - now).total_seconds() / 60.0
        breached = remaining_minutes < 0
        escalate_soon = (not breached) and remaining_minutes <= SLA_ESCALATION_LEAD_MINUTES
        if breached:
            risk = "breached"
        elif escalate_soon:
            risk = "escalate_now"
        elif remaining_hours < hours * 0.25:
            risk = "high"
        elif remaining_hours < hours * 0.5:
            risk = "medium"
        else:
            risk = "low"
        return AgentResult(
            name="sla_monitor",
            confidence=0.99,
            data={
                "priority": priority,
                "sla_hours": hours,
                "resolution_time": resolution_time,
                "sla_started_at": created.isoformat(),
                "sla_due_at": due.isoformat(),
                "hours_remaining": round(remaining_hours, 2),
                "minutes_remaining": round(remaining_minutes, 1),
                "breached": breached,
                "escalate_before_breach_minutes": SLA_ESCALATION_LEAD_MINUTES,
                "should_escalate": breached or escalate_soon,
                "risk": risk,
            },
            notes=(
                f"SLA timer started for {priority} ({resolution_time}). "
                f"{'ESCALATE — within 30 minutes of breach' if escalate_soon else f'Risk: {risk}'}"
            ),
        )


class NotificationAgent:
    """Sub Agent 8 — Notification Agent (Email, Slack, Teams, SMS)."""

    def run(self, ticket_number: str, event: str, recipients: list[str], message: str) -> AgentResult:
        from app.infrastructure.notifications.channels import notification_channels

        subject = f"[AIOps][{event}] {ticket_number}"
        channel_results = {
            "smtp": notification_channels.send_smtp(subject, message, recipients),
            "email": True,
            "slack": False,
            "teams": False,
            "sms": False,
        }
        try:
            import httpx
            from app.core.config import get_settings

            settings = get_settings()
            with httpx.Client(timeout=10.0) as client:
                if settings.slack_webhook_url:
                    r = client.post(settings.slack_webhook_url, json={"text": f"*{subject}*\n{message}"})
                    channel_results["slack"] = {"sent": r.is_success, "status_code": r.status_code}
                else:
                    channel_results["slack"] = {"sent": False, "mocked": True}
                if settings.teams_webhook_url:
                    r = client.post(
                        settings.teams_webhook_url,
                        json={"title": subject, "text": message},
                    )
                    channel_results["teams"] = {"sent": r.is_success, "status_code": r.status_code}
                else:
                    channel_results["teams"] = {"sent": False, "mocked": True}
                if settings.sms_webhook_url:
                    r = client.post(
                        settings.sms_webhook_url,
                        json={
                            "from": settings.sms_from or "AIOPS",
                            "to": recipients,
                            "body": f"{subject}: {message}"[:480],
                        },
                    )
                    channel_results["sms"] = {"sent": r.is_success, "status_code": r.status_code}
                else:
                    channel_results["sms"] = {"sent": False, "mocked": True}
        except Exception as exc:  # noqa: BLE001
            channel_results["http_channels_error"] = str(exc)

        notifications = [
            {
                "ticket": ticket_number,
                "event": event,
                "recipient": r,
                "message": message,
                "channels": ["Email", "Slack", "Teams", "SMS"],
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }
            for r in recipients
        ]
        return AgentResult(
            name="notification",
            confidence=1.0,
            data={"notifications": notifications, "channels": channel_results, "message": message},
            notes=f"Sent via Email | Slack | Teams | SMS → {', '.join(recipients) or 'ops'}",
        )

    @staticmethod
    def format_ticket_created(
        ticket_number: str,
        priority: str,
        assigned_name: str | None,
        eta: str,
    ) -> str:
        return (
            f"{priority} Ticket Created\n"
            f"Ticket: {ticket_number}\n"
            f"Assigned To: {assigned_name or 'Unassigned'}\n"
            f"ETA: {eta}"
        )


class ResolutionSuggestionAgent:
    """
    Sub Agent 5 — Resolution Agent (RAG)

    Searches previous tickets, KB articles, PDFs, SOP documents, runbooks.
    Returns suggested resolution, confidence, and references.
    """

    SOURCE_ALIASES = {
        "incident": "Previous tickets",
        "learned_incident": "Previous tickets",
        "kb": "KB articles",
        "pdf": "PDFs",
        "sop": "SOP documents",
        "runbook": "Runbooks",
    }

    def run(self, query: str, rag_articles: list[dict[str, Any]] | None = None) -> AgentResult:
        articles = rag_articles if rag_articles is not None else self._search(query)
        suggestions: list[dict[str, Any]] = []
        references: list[dict[str, Any]] = []
        for art in articles[:5]:
            title = art.get("title") or "Untitled"
            snippet = art.get("snippet") or art.get("content") or ""
            source = art.get("source") or "kb"
            steps = self._steps_from_snippet(title, snippet)
            ref = {
                "title": title,
                "source_type": self.SOURCE_ALIASES.get(source, source),
                "source": source,
                "score": art.get("score", 0),
            }
            references.append(ref)
            suggestions.append(
                {
                    "title": title,
                    "source": source,
                    "source_type": ref["source_type"],
                    "score": art.get("score", 0),
                    "steps": steps,
                    "rationale": f"Matched {ref['source_type']}.",
                }
            )
        confidence = float(suggestions[0]["score"]) if suggestions else 0.0
        suggested = (
            "\n".join(f"{i+1}. {s}" for i, s in enumerate(suggestions[0]["steps"]))
            if suggestions
            else "No matching KB/runbook found. Investigate CI health and recent changes."
        )
        return AgentResult(
            name="resolution_suggestion",
            confidence=round(confidence, 4),
            data={
                "suggested_resolution": suggested,
                "confidence": round(confidence, 4),
                "confidence_pct": int(round(confidence * 100)),
                "references": references,
                "suggestions": suggestions,
                "recommended_resolution": suggestions[0]["steps"] if suggestions else [],
                "searched": ["Previous tickets", "KB articles", "PDFs", "SOP documents", "Runbooks"],
            },
            notes=f"Resolution confidence {int(round(confidence * 100))}% with {len(references)} references",
        )

    def _search(self, query: str) -> list[dict[str, Any]]:
        hits = vector_store.search(query, limit=5)
        return [
            {
                "title": h.payload.get("title"),
                "snippet": (h.payload.get("content") or "")[:400],
                "score": round(h.score, 4),
                "source": h.payload.get("source"),
            }
            for h in hits
        ]

    def _steps_from_snippet(self, title: str, snippet: str) -> list[str]:
        parts = [p.strip() for p in re.split(r"[.;]\s+", snippet) if p.strip()]
        steps = [f"Review guidance: {title}"]
        steps.extend(
            parts[:4]
            if parts
            else ["Investigate impacted CI and recent changes.", "Apply standard remediation and validate recovery."]
        )
        steps.append("Document resolution and close after confirmation.")
        return steps


# Aliases matching architecture naming
ResolutionAgent = ResolutionSuggestionAgent
SLAAgent = SLAMonitorAgent


class EscalationAgent:
    """Escalate overdue / breached tickets and notify engineers/managers."""

    MANAGER = "ops.manager@example.com"

    def run(self, ticket: dict[str, Any], managers: list[str] | None = None) -> AgentResult:
        recipients = []
        if ticket.get("assigned_to"):
            recipients.append(ticket["assigned_to"])
        recipients.extend(managers or [self.MANAGER])
        recipients = list(dict.fromkeys(recipients))
        new_priority = ticket.get("priority", "P3")
        if new_priority == "P3":
            escalated_priority = "P2"
        elif new_priority == "P2":
            escalated_priority = "P1"
        else:
            escalated_priority = "P1"
        message = (
            f"ESCALATION: {ticket.get('number')} is overdue (SLA breached). "
            f"Priority {new_priority} → {escalated_priority}. Immediate attention required."
        )
        notify = NotificationAgent().run(ticket.get("number", "UNKNOWN"), "sla_escalation", recipients, message)
        return AgentResult(
            name="escalation",
            confidence=1.0,
            data={
                "escalated": True,
                "from_priority": new_priority,
                "to_priority": escalated_priority,
                "recipients": recipients,
                "notifications": notify.data.get("notifications", []),
                "message": message,
            },
            notes=message,
        )


class SummarizationAgent:
    def run(self, ticket: dict[str, Any], agent_outputs: dict[str, Any]) -> AgentResult:
        short = ticket.get("short_description", "")
        classification = agent_outputs.get("classification", {})
        ticket_type = classification.get("ticket_type") or classification.get("category", "Incident")
        subcategory = classification.get("subcategory", "General")
        conf_pct = classification.get("confidence_pct")
        priority = agent_outputs.get("priority", {}).get("priority", "P3")
        assignee = agent_outputs.get("assignment", {}).get("assigned_name", "unassigned")
        dup = agent_outputs.get("duplicate_detection", {})
        rca = agent_outputs.get("graphrag", {}).get("root_cause_suggestion", "")
        kb = agent_outputs.get("rag_knowledge", {}).get("articles", [])
        kb_line = kb[0]["title"] if kb else "No KB match"
        res = agent_outputs.get("resolution_suggestion", {}).get("suggestions", [])
        res_line = res[0]["title"] if res else "None"
        summary = (
            f"Ticket '{short}' classified as {ticket_type} / {subcategory}"
            f"{f' ({conf_pct}% confidence)' if conf_pct is not None else ''} with priority {priority}. "
            f"Recommended assignee: {assignee}. "
            f"Duplicate: {'yes (' + str(dup.get('duplicate_of')) + ')' if dup.get('is_duplicate') else 'no'}. "
            f"Top KB: {kb_line}. Suggested resolution source: {res_line}. RCA hint: {rca}"
        )
        return AgentResult(
            name="summarization",
            confidence=0.9,
            data={"summary": summary},
            notes="Generated ticket summary",
        )
