from __future__ import annotations

import logging
from typing import Any, TypedDict

from app.agents.sub_agents import (
    AssignmentAgent,
    ClassificationAgent,
    DuplicateDetectionAgent,
    EscalationAgent,
    GraphRAGAgent,
    NotificationAgent,
    PriorityAgent,
    RAGKnowledgeAgent,
    ResolutionSuggestionAgent,
    SLAMonitorAgent,
    SummarizationAgent,
)
from app.domain.ticket_workflow import TICKET_WORKFLOW

logger = logging.getLogger(__name__)

# Exact orchestration order from the product Ticket Workflow
# Agents run by Master before Create ServiceNow + Notify (application layer)
WORKFLOW_AGENT_ORDER = [
    "classification",
    "priority",
    "duplicate_check",
    "assignment",
    "knowledge_search",
    "graphrag_analysis",
    "sla_monitor",
]


class AgentState(TypedDict, total=False):
    short_description: str
    description: str
    configuration_item: str | None
    caller: str
    engineers: list[dict[str, Any]]
    existing_tickets: list[dict[str, Any]]
    ticket_number: str
    results: dict[str, Any]
    workflow_trace: list[dict[str, Any]]
    overall_confidence: float
    errors: list[str]


def _trace(state: AgentState, step_id: str, title: str, status: str = "completed", detail: str = "") -> None:
    state.setdefault("workflow_trace", []).append(
        {"id": step_id, "title": title, "status": status, "detail": detail}
    )


class MasterAgent:
    """
    Master Agent orchestrates the Ticket Workflow:

    Classification → Priority → Duplicate Check → Assignment →
    Knowledge Search → GraphRAG Analysis → Create ServiceNow Ticket →
    Notify Engineer → Work In Progress → Resolution → Closed

    Steps after GraphRAG (ServiceNow create + notify + lifecycle) run in TicketService.
    """

    def __init__(self) -> None:
        self.classification = ClassificationAgent()
        self.priority = PriorityAgent()
        self.assignment = AssignmentAgent()
        self.duplicate = DuplicateDetectionAgent()
        self.rag = RAGKnowledgeAgent()
        self.resolution = ResolutionSuggestionAgent()
        self.graphrag = GraphRAGAgent()
        self.sla = SLAMonitorAgent()
        self.notification = NotificationAgent()
        self.escalation = EscalationAgent()
        self.summarization = SummarizationAgent()
        self._graph = self._build_langgraph()

    def _build_langgraph(self):
        try:
            from langgraph.graph import END, StateGraph

            graph = StateGraph(AgentState)

            def classify(state: AgentState) -> AgentState:
                result = self.classification.run(state["short_description"], state["description"])
                state.setdefault("results", {})["classification"] = {**result.data, "confidence": result.confidence}
                _trace(state, "classification", "Classification Agent", detail=result.notes)
                return state

            def prioritize(state: AgentState) -> AgentState:
                result = self.priority.run(state["short_description"], state["description"])
                state.setdefault("results", {})["priority"] = {**result.data, "confidence": result.confidence}
                _trace(state, "priority", "Priority Agent", detail=result.notes)
                return state

            def detect_dup(state: AgentState) -> AgentState:
                result = self.duplicate.run(
                    state["short_description"], state["description"], state.get("existing_tickets", [])
                )
                state.setdefault("results", {})["duplicate_detection"] = {
                    **result.data,
                    "confidence": result.confidence,
                }
                _trace(state, "duplicate_check", "Duplicate Check", detail=result.notes)
                return state

            def assign(state: AgentState) -> AgentState:
                classification = state.get("results", {}).get("classification", {})
                skill_domain = classification.get("subcategory") or classification.get("category") or "General"
                result = self.assignment.run(skill_domain, state.get("engineers", []))
                state.setdefault("results", {})["assignment"] = {**result.data, "confidence": result.confidence}
                _trace(state, "assignment", "Assignment Agent", detail=result.notes)
                return state

            def knowledge_search(state: AgentState) -> AgentState:
                query = f"{state['short_description']}\n{state['description']}"
                rag_result = self.rag.run(query)
                state.setdefault("results", {})["rag_knowledge"] = {
                    **rag_result.data,
                    "confidence": rag_result.confidence,
                }
                resolution = self.resolution.run(query, rag_articles=rag_result.data.get("articles", []))
                state.setdefault("results", {})["resolution_suggestion"] = {
                    **resolution.data,
                    "confidence": resolution.confidence,
                }
                _trace(
                    state,
                    "knowledge_search",
                    "Knowledge Search",
                    detail=f"{rag_result.notes}; {resolution.notes}",
                )
                return state

            def graphrag_analysis(state: AgentState) -> AgentState:
                result = self.graphrag.run(state.get("configuration_item"), state["description"])
                state.setdefault("results", {})["graphrag"] = {**result.data, "confidence": result.confidence}
                _trace(state, "graphrag", "GraphRAG Analysis", detail=result.notes)
                return state

            def sla(state: AgentState) -> AgentState:
                priority = state.get("results", {}).get("priority", {}).get("priority", "P3")
                due = state.get("results", {}).get("priority", {}).get("sla_due_at")
                result = self.sla.run(priority, sla_due_at=due)
                state.setdefault("results", {})["sla_monitor"] = {**result.data, "confidence": result.confidence}
                return state

            def summarize(state: AgentState) -> AgentState:
                ticket = {
                    "short_description": state["short_description"],
                    "description": state["description"],
                }
                result = self.summarization.run(ticket, state.get("results", {}))
                state.setdefault("results", {})["summarization"] = {**result.data, "confidence": result.confidence}
                confidences = [
                    v.get("confidence", 0)
                    for v in state.get("results", {}).values()
                    if isinstance(v, dict) and "confidence" in v
                ]
                state["overall_confidence"] = round(sum(confidences) / len(confidences), 4) if confidences else 0.0
                _trace(
                    state,
                    "handoff",
                    "Handoff to Create ServiceNow Ticket",
                    status="completed",
                    detail="Next: Create ServiceNow → Notify → Status lifecycle (NEW→…→CLOSED)",
                )
                state.setdefault("results", {})["workflow"] = {
                    "definition": TICKET_WORKFLOW,
                    "trace": state.get("workflow_trace", []),
                    "pending_after_create": [
                        "Create ServiceNow Ticket",
                        "Notify Engineer",
                        "NEW → ASSIGNED → WORK IN PROGRESS → WAITING FOR CUSTOMER → RESOLVED → COMPLETED → CLOSED",
                    ],
                }
                return state

            graph.add_node("classify", classify)
            graph.add_node("prioritize", prioritize)
            graph.add_node("detect_dup", detect_dup)
            graph.add_node("assign", assign)
            graph.add_node("knowledge_search", knowledge_search)
            graph.add_node("graphrag_analysis", graphrag_analysis)
            graph.add_node("sla", sla)
            graph.add_node("summarize", summarize)

            # Ticket Workflow order through GraphRAG; SN create + notify in TicketService
            graph.set_entry_point("classify")
            graph.add_edge("classify", "prioritize")
            graph.add_edge("prioritize", "detect_dup")
            graph.add_edge("detect_dup", "assign")
            graph.add_edge("assign", "knowledge_search")
            graph.add_edge("knowledge_search", "graphrag_analysis")
            graph.add_edge("graphrag_analysis", "sla")
            graph.add_edge("sla", "summarize")
            graph.add_edge("summarize", END)
            return graph.compile()
        except Exception as exc:  # noqa: BLE001
            logger.warning("LangGraph unavailable, using sequential orchestration: %s", exc)
            return None

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        state: AgentState = {
            "short_description": payload["short_description"],
            "description": payload.get("description", ""),
            "configuration_item": payload.get("configuration_item"),
            "caller": payload.get("caller", "system"),
            "engineers": payload.get("engineers", []),
            "existing_tickets": payload.get("existing_tickets", []),
            "ticket_number": payload.get("ticket_number", "PENDING"),
            "results": {},
            "workflow_trace": [
                {"id": "user", "title": "User", "status": "completed"},
                {"id": "raise_ticket", "title": "Raise Ticket", "status": "completed"},
                {"id": "master_agent", "title": "Master Agent", "status": "running"},
            ],
            "errors": [],
        }
        if self._graph is not None:
            final = self._graph.invoke(state)
            return {
                "results": final.get("results", {}),
                "overall_confidence": final.get("overall_confidence", 0.0),
                "orchestrator": "langgraph",
                "workflow_trace": final.get("workflow_trace", []),
            }
        return self._run_sequential(state)

    def _run_sequential(self, state: AgentState) -> dict[str, Any]:
        results: dict[str, Any] = {}
        state["results"] = results

        def put(name: str, result, step_id: str, title: str) -> None:
            results[name] = {**result.data, "confidence": result.confidence}
            _trace(state, step_id, title, detail=result.notes)

        put("classification", self.classification.run(state["short_description"], state["description"]), "classification", "Classification Agent")
        put("priority", self.priority.run(state["short_description"], state["description"]), "priority", "Priority Agent")
        put(
            "duplicate_detection",
            self.duplicate.run(
                state["short_description"], state["description"], state.get("existing_tickets", [])
            ),
            "duplicate_check",
            "Duplicate Check",
        )
        classification = results.get("classification", {})
        skill_domain = classification.get("subcategory") or classification.get("category") or "General"
        put("assignment", self.assignment.run(skill_domain, state.get("engineers", [])), "assignment", "Assignment Agent")
        query = f"{state['short_description']}\n{state['description']}"
        rag = self.rag.run(query)
        results["rag_knowledge"] = {**rag.data, "confidence": rag.confidence}
        resolution = self.resolution.run(query, rag_articles=rag.data.get("articles", []))
        results["resolution_suggestion"] = {**resolution.data, "confidence": resolution.confidence}
        _trace(state, "knowledge_search", "Knowledge Search", detail=f"{rag.notes}; {resolution.notes}")
        put("graphrag", self.graphrag.run(state.get("configuration_item"), state["description"]), "graphrag", "GraphRAG Analysis")
        put(
            "sla_monitor",
            self.sla.run(
                results.get("priority", {}).get("priority", "P3"),
                sla_due_at=results.get("priority", {}).get("sla_due_at"),
            ),
            "sla_monitor",
            "SLA Timer",
        )
        summary = self.summarization.run(
            {"short_description": state["short_description"], "description": state["description"]},
            results,
        )
        results["summarization"] = {**summary.data, "confidence": summary.confidence}
        _trace(
            state,
            "handoff",
            "Handoff to Create ServiceNow Ticket",
            detail="Next: Create ServiceNow → Notify → Status lifecycle (NEW→…→CLOSED)",
        )
        results["workflow"] = {
            "definition": TICKET_WORKFLOW,
            "trace": state.get("workflow_trace", []),
            "pending_after_create": [
                "Create ServiceNow Ticket",
                "Notify Engineer",
                "NEW → ASSIGNED → WORK IN PROGRESS → WAITING FOR CUSTOMER → RESOLVED → COMPLETED → CLOSED",
            ],
        }
        confidences = [v.get("confidence", 0) for v in results.values() if isinstance(v, dict) and "confidence" in v]
        return {
            "results": results,
            "overall_confidence": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
            "orchestrator": "sequential",
            "workflow_trace": state.get("workflow_trace", []),
        }


master_agent = MasterAgent()
