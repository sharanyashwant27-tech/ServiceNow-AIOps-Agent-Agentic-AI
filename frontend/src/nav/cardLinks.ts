/** Central href map so dashboard/architecture/workflow cards land on the right page. */

export const OPEN_STATES = new Set([
  "NEW",
  "ASSIGNED",
  "WORK IN PROGRESS",
  "WAITING FOR CUSTOMER",
]);

export const CLOSED_STATES = new Set(["RESOLVED", "COMPLETED", "CLOSED"]);

export const DASHBOARD_CARD_HREFS: Record<string, string> = {
  open_tickets: "/tickets?status=open",
  p1_tickets: "/tickets?priority=P1&status=open",
  p2_tickets: "/tickets?priority=P2&status=open",
  p3_tickets: "/tickets?priority=P3&status=open",
  resolved_today: "/tickets?resolved=today",
  sla_breaches: "/tickets?sla=breached",
  average_resolution_time: "/tickets?status=closed",
  agent_performance: "/automation",
};

export const DASHBOARD_CHART_HREFS: Record<string, string> = {
  ticket_trend: "/tickets",
  resolution_trend: "/tickets?status=closed",
  category_distribution: "/tickets",
  engineer_workload: "/workload",
  sla_compliance: "/tickets?sla=breached",
  knowledge_base_usage: "/knowledge",
  ai_confidence_scores: "/automation",
  ai_confidence_by_agent: "/automation",
};

export const ARCH_NODE_HREFS: Record<string, string> = {
  Users: "/",
  "React Service Portal": "/",
  "FastAPI Backend": "/stack",
  "Master AI Agent": "/automation",
  "RAG Engine": "/knowledge",
  "Vector DB + Neo4j GraphRAG": "/knowledge",
  "ServiceNow Database": "/tickets",
  "n8n Workflow": "/automation",
};

export function archAgentHref(agentId: string): string {
  if (agentId.includes("rag") || agentId.includes("knowledge") || agentId.includes("graph")) {
    return "/knowledge";
  }
  if (agentId.includes("sla") || agentId.includes("notif") || agentId.includes("escalat")) {
    return "/automation";
  }
  return "/automation";
}

export function statusStepHref(code: string): string {
  const key = encodeURIComponent(code);
  return `/tickets?state=${key}`;
}

export function workflowStepHref(step: { id?: string; type?: string; title?: string }): string {
  const id = (step.id || "").toLowerCase();
  const title = (step.title || "").toLowerCase();
  if (id.includes("knowledge") || title.includes("knowledge") || title.includes("rag") || title.includes("graph")) {
    return "/knowledge";
  }
  if (id.includes("n8n") || title.includes("n8n") || title.includes("notify") || title.includes("slack")) {
    return "/automation";
  }
  if (title.includes("servicenow") || id.includes("create")) {
    return "/tickets";
  }
  if (step.type === "orchestrator" || step.type === "agent") {
    return "/automation";
  }
  if (step.type === "state") {
    return "/tickets";
  }
  return "/workflow";
}
