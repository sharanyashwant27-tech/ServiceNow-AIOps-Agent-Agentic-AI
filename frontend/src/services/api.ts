const API = "/api/v1";

function authHeaders(): HeadersInit {
  const token = localStorage.getItem("token");
  return token
    ? { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }
    : { "Content-Type": "application/json" };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { ...authHeaders(), ...(init?.headers || {}) },
  });
  const contentType = res.headers.get("content-type") || "";
  if (!res.ok) {
    const detail = contentType.includes("application/json")
      ? await res.json().catch(() => ({}))
      : {};
    throw new Error((detail as { detail?: string }).detail || res.statusText || `HTTP ${res.status}`);
  }
  if (!contentType.includes("application/json")) {
    throw new Error(`Expected JSON from ${path}, got ${contentType || "unknown content type"}`);
  }
  return res.json();
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<{ id: string; email: string; full_name: string; role: string }>("/auth/me"),
  tickets: () => request<any[]>("/tickets"),
  createTicket: (payload: Record<string, unknown>) =>
    request<any>("/tickets", { method: "POST", body: JSON.stringify(payload) }),
  aiTicketDraft: (user_text: string) =>
    request<any>("/tickets/ai-draft", {
      method: "POST",
      body: JSON.stringify({ user_text }),
    }),
  getTicket: (id: string) => request<any>(`/tickets/${id}`),
  updateState: (id: string, state: string, actor: string) =>
    request<any>(`/tickets/${id}/state`, {
      method: "PATCH",
      body: JSON.stringify({ state, actor }),
    }),
  resolutionWorkflow: (id: string, engineer: string, resolution_note?: string, auto_close = true) =>
    request<any>(`/tickets/${id}/resolution-workflow`, {
      method: "POST",
      body: JSON.stringify({ engineer, resolution_note, auto_close }),
    }),
  resolutionWorkflowDefinition: () => request<any>("/automation/resolution-workflow"),
  addWorkNote: (id: string, author: string, body: string, format = "markdown") =>
    request<any>(`/tickets/${id}/work-notes`, {
      method: "POST",
      body: JSON.stringify({ author, body, is_internal: true, format }),
    }),
  addComment: (id: string, author: string, body: string) =>
    request<any>(`/tickets/${id}/comments`, {
      method: "POST",
      body: JSON.stringify({ author, body }),
    }),
  uploadAttachment: async (id: string, file: File) => {
    const token = localStorage.getItem("token");
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API}/tickets/${id}/attachments`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || res.statusText);
    }
    return res.json();
  },
  refreshAiSummary: (id: string) =>
    request<any>(`/tickets/${id}/ai-summary`, { method: "POST", body: "{}" }),
  dashboard: () => request<any>("/dashboard"),
  engineers: () => request<any[]>("/engineers"),
  knowledgeSearch: (q: string) => request<any>(`/knowledge/search?q=${encodeURIComponent(q)}`),
  graphCi: (ci: string) => request<any>(`/graph/ci/${encodeURIComponent(ci)}`),
  searchIncidents: (q: string) => request<any>(`/incidents/search?q=${encodeURIComponent(q)}`),
  ingestAlert: (payload: Record<string, unknown>) =>
    request<any>("/automation/ingest-alert", { method: "POST", body: JSON.stringify(payload) }),
  escalateOverdue: () => request<any>("/automation/escalate-overdue", { method: "POST", body: "{}" }),
  slaBreachWorkflowDefinition: () => request<any>("/automation/sla-breach-workflow"),
  slaBreachWorkflowRun: () =>
    request<any>("/automation/sla-breach-workflow/run", { method: "POST", body: "{}" }),
  slaBreachWorkflowLogs: () => request<any>("/automation/sla-breach-workflow/logs"),
  capabilities: () => request<any>("/automation/capabilities"),
  techStack: () => request<any>("/stack/tech"),
  architecture: () => request<any>("/stack/architecture"),
  ticketWorkflow: () => request<any>("/stack/ticket-workflow"),
  ticketStatus: () => request<any>("/stack/ticket-status"),
  ticketEntity: () => request<any>("/stack/ticket-entity"),
  ragQuery: (q: string) => request<any>(`/stack/rag/query?q=${encodeURIComponent(q)}`, { method: "POST" }),
  ragPipelineDefinition: () => request<any>("/stack/rag-pipeline"),
  ragPipeline: (q: string) =>
    request<any>(`/stack/rag/pipeline?q=${encodeURIComponent(q)}`, { method: "POST" }),
  graphRagPipelineDefinition: () => request<any>("/stack/graphrag-pipeline"),
  graphRagPipeline: (ci: string, description = "") =>
    request<any>(
      `/stack/graphrag/pipeline?ci=${encodeURIComponent(ci)}&description=${encodeURIComponent(description)}`,
      { method: "POST" }
    ),
  n8nWorkflowDefinition: () => request<any>("/stack/n8n-workflow"),
  n8nWorkflowLogs: () => request<any>("/stack/n8n-workflow/logs"),
  n8nTicketCreatedRun: (short_description: string, description = "") =>
    request<any>(
      `/stack/n8n-workflow/ticket-created?short_description=${encodeURIComponent(short_description)}&description=${encodeURIComponent(description)}`,
      { method: "POST" }
    ),
};
