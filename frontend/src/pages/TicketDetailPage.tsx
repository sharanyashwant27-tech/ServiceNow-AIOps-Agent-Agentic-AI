import { FormEvent, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import ActivityNotesViewer from "../components/ActivityNotesViewer";
import { api } from "../services/api";
import { useAuth } from "../hooks/useAuth";
import {
  formatDate,
  ticketAssignment,
  ticketCompletedAt,
  ticketCreatedAt,
  ticketStatus,
} from "../utils/dates";

const STATES = [
  "New",
  "Assigned",
  "Work In Progress",
  "Waiting for Customer",
  "Resolved",
  "Completed",
  "Closed",
];

export default function TicketDetailPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const [ticket, setTicket] = useState<any>(null);
  const [note, setNote] = useState("");
  const [comment, setComment] = useState("");
  const [uploading, setUploading] = useState(false);
  const [refreshingSummary, setRefreshingSummary] = useState(false);
  const [resolutionNote, setResolutionNote] = useState("Restarted Outlook Cache / applied fix and validated with user.");
  const [resolving, setResolving] = useState(false);
  const [resolutionRun, setResolutionRun] = useState<any>(null);

  async function load() {
    if (!id) return;
    setTicket(await api.getTicket(id));
  }

  useEffect(() => {
    load().catch(console.error);
  }, [id]);

  if (!ticket) return <p>Loading ticket…</p>;

  async function changeState(state: string) {
    setTicket(await api.updateState(ticket.id, state, user?.email || "system"));
  }

  async function runResolutionWorkflow() {
    setResolving(true);
    try {
      const res = await api.resolutionWorkflow(
        ticket.id,
        user?.email || "engineer@example.com",
        resolutionNote,
        true
      );
      setResolutionRun(res);
      setTicket(res.ticket);
    } catch (err: any) {
      alert(err.message || "Resolution workflow failed");
    } finally {
      setResolving(false);
    }
  }

  async function submitNote(e: FormEvent) {
    e.preventDefault();
    setTicket(await api.addWorkNote(ticket.id, user?.email || "engineer", note, "markdown"));
    setNote("");
  }

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      setTicket(await api.uploadAttachment(ticket.id, file));
    } catch (err: any) {
      alert(err.message || "Upload failed");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  async function onRefreshSummary() {
    setRefreshingSummary(true);
    try {
      setTicket(await api.refreshAiSummary(ticket.id));
    } finally {
      setRefreshingSummary(false);
    }
  }

  async function submitComment(e: FormEvent) {
    e.preventDefault();
    setTicket(await api.addComment(ticket.id, user?.email || "user", comment));
    setComment("");
  }

  const agents = ticket.metadata?.agent_results || {};
  const suggestions = ticket.metadata?.resolution_suggestions || agents.resolution_suggestion?.suggestions || [];
  const workflowTrace = ticket.metadata?.workflow_trace || [];

  return (
    <div className="page">
      <header className="page-header">
        <h1>
          {ticket.number} · {ticket.title || ticket.short_description}
        </h1>
        <p>
          <span className="status-chip">{ticketStatus(ticket)}</span>
          {" · "}
          <span className={`pill p-${ticket.priority}`}>{ticket.priority}</span>
          {" · "}
          {ticketAssignment(ticket)}
          {" · created "}
          {formatDate(ticketCreatedAt(ticket))}
          {ticketCompletedAt(ticket) ? ` · completed ${formatDate(ticketCompletedAt(ticket))}` : ""}
        </p>
        <p>{ticket.ai_summary}</p>
      </header>

      <div className="grid-2">
        <section className="panel">
          <h2>Ticket entity</h2>
          <dl className="kv">
            <div>
              <dt>id</dt>
              <dd>{ticket.id}</dd>
            </div>
            <div>
              <dt>title</dt>
              <dd>{ticket.title || ticket.short_description}</dd>
            </div>
            <div>
              <dt>status</dt>
              <dd>
                <span className="status-chip">{ticketStatus(ticket)}</span>
              </dd>
            </div>
            <div>
              <dt>priority / resolution_due</dt>
              <dd>
                {ticket.priority} ·{" "}
                {ticket.resolution_due || ticket.sla_due_at
                  ? formatDate(ticket.resolution_due || ticket.sla_due_at)
                  : "—"}
              </dd>
            </div>
            <div>
              <dt>category / subcategory</dt>
              <dd>
                {ticket.category} / {ticket.subcategory}
              </dd>
            </div>
            <div>
              <dt>assignment</dt>
              <dd>{ticketAssignment(ticket)}</dd>
            </div>
            <div>
              <dt>assigned_to</dt>
              <dd>{ticket.assigned_to || "Unassigned"}</dd>
            </div>
            <div>
              <dt>assignment_group</dt>
              <dd>{ticket.assignment_group || "—"}</dd>
            </div>
            <div>
              <dt>created_by</dt>
              <dd>{ticket.created_by || ticket.caller || "—"}</dd>
            </div>
            <div>
              <dt>created_date</dt>
              <dd>{formatDate(ticketCreatedAt(ticket))}</dd>
            </div>
            <div>
              <dt>completed_date</dt>
              <dd>{formatDate(ticketCompletedAt(ticket))}</dd>
            </div>
            <div>
              <dt>sla</dt>
              <dd>
                {ticket.sla?.resolution_time || "—"}
                {ticket.sla?.breached ? " · breached" : ""}
              </dd>
            </div>
            <div>
              <dt>embeddings</dt>
              <dd>dim {ticket.embeddings_dim || (ticket.embeddings || []).length}</dd>
            </div>
            <div>
              <dt>CI</dt>
              <dd>{ticket.configuration_item || "—"}</dd>
            </div>
          </dl>
          {!!(ticket.knowledge_links || []).length && (
            <>
              <h2 style={{ marginTop: "1rem" }}>knowledge_links</h2>
              <ul className="list compact">
                {ticket.knowledge_links.map((k: any, i: number) => (
                  <li key={k.id || i}>
                    <div>
                      <strong>{k.title}</strong>
                      <span>
                        {k.source} · {Math.round((k.score || 0) * 100)}%
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
          {!!(ticket.related_incidents || []).length && (
            <>
              <h2 style={{ marginTop: "1rem" }}>related_incidents</h2>
              <ul className="list compact">
                {ticket.related_incidents.map((r: any, i: number) => (
                  <li key={r.id || i}>
                    <div>
                      <strong>
                        {r.number || r.id} · {r.relation}
                      </strong>
                      <span>
                        {r.title} ({Math.round((r.score || 0) * 100)}%)
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
          <p className="rca">{ticket.root_cause_suggestion}</p>
          {!!workflowTrace.length && (
            <>
              <h2 style={{ marginTop: "1rem" }}>Ticket workflow</h2>
              <ul className="workflow-trace">
                {workflowTrace
                  .filter((s: any) => s.kind !== "status")
                  .map((s: any, idx: number) => (
                    <li key={`${s.id}-${idx}`}>
                      <span>{s.title}</span>
                      <span className={s.status === "completed" ? "ok" : s.status === "skipped" ? "skipped" : "pending"}>
                        {s.status}
                      </span>
                    </li>
                  ))}
              </ul>
              <h2 style={{ marginTop: "1rem" }}>Ticket status</h2>
              <ul className="workflow-trace">
                {(workflowTrace.filter((s: any) => s.kind === "status").length
                  ? workflowTrace.filter((s: any) => s.kind === "status")
                  : STATES.map((title) => ({
                      id: title,
                      title,
                      status: title === ticket.state ? "completed" : "pending",
                    }))
                ).map((s: any, idx: number) => (
                  <li key={`${s.id}-${idx}`}>
                    <span>{s.title}</span>
                    <span
                      className={
                        s.title === ticket.state
                          ? "ok"
                          : s.status === "completed"
                            ? "ok"
                            : s.status === "skipped"
                              ? "skipped"
                              : "pending"
                      }
                    >
                      {s.title === ticket.state ? "current" : s.status}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
          <div className="state-actions">
            {STATES.map((s) => (
              <button
                key={s}
                className={s === (ticket.status || ticket.state) ? "active" : "ghost"}
                onClick={() => changeState(s)}
              >
                {s}
              </button>
            ))}
          </div>

          <section className="resolution-box">
            <h2>Resolution Workflow</h2>
            <p className="hint">Engineer → Resolve → AI Verify → Customer Email → Close → Store Embedding</p>
            <label>
              Resolution note
              <textarea
                value={resolutionNote}
                onChange={(e) => setResolutionNote(e.target.value)}
                rows={3}
                placeholder="Describe the fix applied…"
              />
            </label>
            <button type="button" onClick={runResolutionWorkflow} disabled={resolving}>
              {resolving ? "Running…" : "Run Resolution Workflow"}
            </button>
            {resolutionRun && (
              <ul className="workflow-trace" style={{ marginTop: "0.75rem" }}>
                {(resolutionRun.trace || []).map((s: any) => (
                  <li key={s.id}>
                    <span>{s.title}</span>
                    <span className={s.status === "completed" ? "ok" : s.status === "failed" ? "pending" : "skipped"}>
                      {s.detail || s.status}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {ticket.metadata?.resolution_workflow && !resolutionRun && (
              <p className="hint" style={{ marginTop: "0.5rem" }}>
                Last run: AI Verify{" "}
                {ticket.metadata.resolution_workflow.ai_verify?.verified ? "passed" : "needs review"} ·{" "}
                {ticket.metadata.resolution_workflow.closed ? "Closed" : "Resolved"}
              </p>
            )}
          </section>
        </section>

        <section className="panel">
          <h2>RAG resolution suggestions</h2>
          <ul className="list">
            {suggestions.map((s: any, idx: number) => (
              <li key={idx}>
                <div>
                  <strong>
                    {s.title} · {s.source} ({Math.round((s.score || 0) * 100)}%)
                  </strong>
                  <span>{(s.steps || []).join(" → ")}</span>
                </div>
              </li>
            ))}
          </ul>
          {!suggestions.length && <p className="hint">No suggestions yet.</p>}
          <h2 style={{ marginTop: "1rem" }}>Agent outputs</h2>
          <pre className="code">{JSON.stringify(agents, null, 2)}</pre>
        </section>

        <section className="panel activity-panel">
          <h2>Notes Viewer</h2>
          <p className="hint">Supports Markdown, Images, Attachments, and AI Summary.</p>
          <ActivityNotesViewer
            notes={ticket.activity_notes || []}
            viewerText={ticket.activity_notes_viewer}
            aiSummary={ticket.ai_summary}
            attachments={ticket.attachments || []}
            images={ticket.images || []}
            supports={ticket.notes_viewer_supports || []}
            onRefreshSummary={onRefreshSummary}
            refreshingSummary={refreshingSummary}
          />
          <form onSubmit={submitNote} className="note-compose" style={{ marginTop: "1rem" }}>
            <label>
              Activity note (Markdown)
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={"**Investigated VPN**\n\n- Checked gateway logs\n- Restarted service"}
                rows={4}
                required
              />
            </label>
            <div className="note-compose-actions">
              <button type="submit">Add note</button>
              <label className="upload-btn">
                {uploading ? "Uploading…" : "Attach file / image"}
                <input type="file" onChange={onUpload} disabled={uploading} hidden />
              </label>
            </div>
          </form>
        </section>

        <section className="panel">
          <h2>Comments & audit</h2>
          <ul className="list">
            {(ticket.comments || []).map((c: any) => (
              <li key={c.id}>
                <div>
                  <strong>{c.author}</strong>
                  <span>{c.body}</span>
                </div>
              </li>
            ))}
          </ul>
          <form onSubmit={submitComment} className="inline-form">
            <input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Add comment" required />
            <button>Add</button>
          </form>
          <ul className="list compact">
            {(ticket.audit_logs || []).map((a: any) => (
              <li key={a.id}>
                <div>
                  <strong>{a.action}</strong>
                  <span>
                    {a.actor} · {JSON.stringify(a.details)}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
