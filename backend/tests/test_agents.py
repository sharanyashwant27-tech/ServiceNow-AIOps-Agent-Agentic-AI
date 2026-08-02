from app.agents.master_agent import master_agent
from app.agents.sub_agents import (
    AssignmentAgent,
    ClassificationAgent,
    DuplicateDetectionAgent,
    EscalationAgent,
    GraphRAGAgent,
    NotificationAgent,
    PriorityAgent,
    ResolutionSuggestionAgent,
    SLAMonitorAgent,
)
from app.domain.value_objects.ticket_state import Priority


def test_priority_email_server_down_is_p1():
    result = PriorityAgent().run("Email server down", "")
    assert result.data["priority"] == Priority.P1.value
    assert result.data["resolution_time"] == "2 Hours"
    assert result.data["label"] == "Critical Production Down"


def test_ticket_classification_vpn_not_working():
    result = ClassificationAgent().run("VPN not working", "")
    assert result.data["category"] == "Incident"
    assert result.data["subcategory"] == "Network"
    assert result.data["confidence_pct"] >= 98


def test_assignment_network_to_john():
    engineers = [
        {
            "name": "John",
            "email": "john@example.com",
            "skills": ["Network", "Infrastructure", "VPN"],
            "assignment_group": "Infrastructure",
            "team": "Infrastructure",
            "max_workload": 8,
            "current_workload": 1,
            "active": True,
            "available": True,
            "shift": "Day",
            "experience_years": 8,
        },
        {
            "name": "Chloe Apps",
            "email": "chloe.apps@example.com",
            "skills": ["Application", "API"],
            "assignment_group": "App Support",
            "team": "App Support",
            "max_workload": 8,
            "current_workload": 3,
            "active": True,
            "available": True,
            "shift": "Day",
            "experience_years": 4,
        },
    ]
    result = AssignmentAgent().run("Network", engineers)
    assert result.data["assigned_name"] == "John"
    assert result.data["team"] == "Infrastructure"


def test_duplicate_threshold_90():
    agent = DuplicateDetectionAgent()
    existing = [
        {
            "number": "INC100010",
            "short_description": "VPN not working for users",
            "description": "VPN not working for users in office",
        }
    ]
    result = agent.run("VPN not working for users", "VPN not working for users in office", existing)
    assert result.data["threshold"] == 0.9
    assert result.data["is_duplicate"] is True
    assert result.data["action"] == "link_existing_ticket"


def test_resolution_agent_returns_references():
    result = ResolutionSuggestionAgent().run("email server down")
    assert "suggested_resolution" in result.data
    assert "references" in result.data
    assert "Previous tickets" in result.data["searched"]


def test_graphrag_storage_impact():
    result = GraphRAGAgent().run("Storage-D", "Storage failure")
    assert "Storage-D" in result.data["impact_chain"]
    assert "Application-B" in result.data["affected_services"] or "Database-C" in result.data["affected_services"]


def test_sla_agent_escalation_window():
    result = SLAMonitorAgent().run("P1")
    assert result.data["resolution_time"] == "2 Hours"
    assert result.data["escalate_before_breach_minutes"] == 30


def test_notification_format():
    msg = NotificationAgent.format_ticket_created("INC100001", "P1", "John", "2 Hours")
    assert "P1 Ticket Created" in msg
    assert "Assigned To: John" in msg
    assert "ETA: 2 Hours" in msg


def test_master_agent_orchestration():
    out = master_agent.run(
        {
            "short_description": "Email server down",
            "description": "Production email server is down for all users",
            "configuration_item": "EMAIL-GATEWAY",
            "caller": "ops@example.com",
            "engineers": [
                {
                    "name": "John",
                    "email": "john@example.com",
                    "skills": ["Network", "Infrastructure", "Email"],
                    "assignment_group": "Infrastructure",
                    "team": "Infrastructure",
                    "max_workload": 8,
                    "current_workload": 1,
                    "active": True,
                    "available": True,
                    "shift": "Day",
                    "experience_years": 8,
                }
            ],
            "existing_tickets": [],
            "ticket_number": "INC100001",
        }
    )
    assert out["results"]["priority"]["priority"] == "P1"
    assert out["results"]["assignment"]["assigned_name"] == "John"
    assert out["results"]["graphrag"]
    assert out["results"]["rag_knowledge"]
    titles = [s["title"] for s in out.get("workflow_trace", [])]
    assert "Classification Agent" in titles
    assert "GraphRAG Analysis" in titles
    assert "Handoff to Create ServiceNow Ticket" in titles


def test_rag_pipeline_definition():
    from app.domain.rag_pipeline import RAG_PIPELINE

    titles = [s["title"] for s in RAG_PIPELINE["steps"]]
    assert titles == [
        "User Query",
        "Embedding",
        "Vector Search",
        "Retrieve Similar Tickets",
        "Retrieve KB Articles",
        "Retrieve SOP",
        "LLM",
        "Final Resolution",
    ]


def test_n8n_ticket_created_workflow_definition():
    from app.domain.n8n_workflow import N8N_TICKET_CREATED_WORKFLOW

    titles = [s["title"] for s in N8N_TICKET_CREATED_WORKFLOW["steps"]]
    assert titles == [
        "Ticket Created : Webhook",
        "AI Classification",
        "Priority",
        "Assignment",
        "ServiceNow API",
        "Email",
        "Slack",
        "Log Database",
    ]


def test_sla_breach_workflow_definition():
    from app.domain.sla_breach_workflow import SLA_BREACH_WORKFLOW

    titles = [s["title"] for s in SLA_BREACH_WORKFLOW["steps"]]
    assert titles == [
        "Cron",
        "Find Expired SLA",
        "Notify Manager",
        "Escalate",
        "Create RCA Task",
    ]


def test_resolution_workflow_definition_and_verify():
    from app.domain.resolution_workflow import RESOLUTION_WORKFLOW
    from app.infrastructure.automation.resolution_workflow import ResolutionWorkflow

    titles = [s["title"] for s in RESOLUTION_WORKFLOW["steps"]]
    assert titles == [
        "Engineer",
        "Resolve Ticket",
        "AI Verify",
        "Customer Email",
        "Close Ticket",
        "Store Embedding",
    ]

    class T:
        work_notes = [{"body": "Restarted Outlook Cache and resolved"}]
        short_description = "Outlook Application Failure"
        description = "My Outlook is not opening after today's update."
        ai_summary = "Software / P2"
        is_duplicate_of = None
        state = "Work In Progress"
        priority = "P2"

    verify = ResolutionWorkflow()._ai_verify(T())  # type: ignore[arg-type]
    assert verify["verified"] is True


def test_graphrag_pipeline_storage():
    from app.domain.graphrag_pipeline import GRAPHRAG_PIPELINE
    from app.infrastructure.graph.pipeline import graphrag_pipeline

    titles = [s["title"] for s in GRAPHRAG_PIPELINE["steps"]]
    assert titles == [
        "Ticket",
        "Neo4j",
        "Find Related CI",
        "Find Dependencies",
        "Find Previous Failures",
        "Generate RCA",
        "Return Impact Analysis",
    ]
    out = graphrag_pipeline.run(
        ticket={"number": "INC100001", "title": "Storage failure", "description": "Storage-D offline"},
        ci="Storage-D",
    )
    assert out["related_ci"] == "Storage-D"
    assert "Application-B" in (out.get("affected_services") or out.get("impact_chain") or [])
    assert out["rca"]
    assert out["trace"][-1]["title"] == "Return Impact Analysis"


def test_ai_ticket_creation_outlook():
    from app.agents.ai_ticket_creation import ai_ticket_creation_agent

    out = ai_ticket_creation_agent.generate(
        "My Outlook is not opening after today's update.",
        [{"name": "Sam Desktop", "email": "sam.desktop@example.com", "assignment_group": "Desktop Team", "skills": ["Outlook"], "active": True}],
    )
    g = out["generated"]
    assert g["Title"] == "Outlook Application Failure"
    assert g["Category"] == "Software"
    assert g["Priority"] == "P2"
    assert g["Assignment"] == "Desktop Team"
    assert g["SLA"] == "4 Hours"
    assert g["Suggested Resolution"] == "Restart Outlook Cache"
    assert g["Related KB"] == "KB-2025-889"


def test_ticket_entity_fields():
    from app.domain.entities.ticket import TICKET_ENTITY_FIELDS

    expected = [
        "id",
        "title",
        "description",
        "priority",
        "status",
        "category",
        "subcategory",
        "assigned_to",
        "created_by",
        "created_date",
        "resolution_due",
        "work_notes",
        "attachments",
        "sla",
        "embeddings",
        "knowledge_links",
        "related_incidents",
    ]
    assert TICKET_ENTITY_FIELDS == expected


def test_activity_notes_viewer_format():
    from app.domain.activity_notes import format_activity_notes_viewer, normalize_activity_notes

    notes = normalize_activity_notes(
        [
            {"id": "1", "body": "Investigated VPN", "created_at": "2026-05-10T10:00:00+00:00", "author": "eng"},
            {"id": "2", "body": "Restarted VPN Gateway", "created_at": "2026-05-10T11:00:00+00:00", "author": "eng"},
            {"id": "3", "body": "Resolved", "created_at": "2026-05-10T12:00:00+00:00", "author": "eng"},
        ]
    )
    viewer = format_activity_notes_viewer(notes)
    assert "2026-05-10" in viewer
    assert "Investigated VPN" in viewer
    assert "Restarted VPN Gateway" in viewer
    assert "Resolved" in viewer
    assert "-------------------" in viewer


def test_escalation_agent():
    esc = EscalationAgent().run(
        {"number": "INC100099", "priority": "P3", "assigned_to": "john@example.com"}
    )
    assert esc.data["to_priority"] == "P2"
