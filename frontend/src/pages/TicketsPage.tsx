import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { CLOSED_STATES, OPEN_STATES } from "../nav/cardLinks";
import { api } from "../services/api";

function isToday(iso: string | null | undefined): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return false;
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

export default function TicketsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [tickets, setTickets] = useState<any[]>([]);
  const [userText, setUserText] = useState("My Outlook is not opening after today's update.");
  const [ci, setCi] = useState("");
  const [draft, setDraft] = useState<any>(null);
  const [generated, setGenerated] = useState<Record<string, string> | null>(null);
  const [generating, setGenerating] = useState(false);
  const [creating, setCreating] = useState(false);
  const [message, setMessage] = useState("");

  const status = searchParams.get("status") || "";
  const priority = searchParams.get("priority") || "";
  const sla = searchParams.get("sla") || "";
  const resolved = searchParams.get("resolved") || "";
  const state = searchParams.get("state") || "";
  const assigned = searchParams.get("assigned") || "";
  const category = searchParams.get("category") || "";

  async function load() {
    setTickets(await api.tickets());
  }

  useEffect(() => {
    load().catch(console.error);
  }, []);

  const filtered = useMemo(() => {
    return tickets.filter((t) => {
      const st = t.status || t.state || "";
      if (status === "open" && !OPEN_STATES.has(st)) return false;
      if (status === "closed" && !CLOSED_STATES.has(st)) return false;
      if (state && st !== state) return false;
      if (priority && t.priority !== priority) return false;
      if (sla === "breached" && !(t.sla_breached || t.sla?.breached)) return false;
      if (resolved === "today") {
        const when = t.resolved_at || t.closed_at || t.updated_at;
        if (!CLOSED_STATES.has(st) || !isToday(when)) return false;
      }
      if (assigned && t.assigned_to !== assigned && !(t.assigned_to || "").startsWith(assigned)) {
        return false;
      }
      if (category && (t.category || "") !== category) return false;
      return true;
    });
  }, [tickets, status, priority, sla, resolved, state, assigned, category]);

  const filterLabel = [
    status && `status=${status}`,
    state && `state=${state}`,
    priority && `priority=${priority}`,
    sla && `sla=${sla}`,
    resolved && `resolved=${resolved}`,
    assigned && `assigned=${assigned}`,
    category && `category=${category}`,
  ]
    .filter(Boolean)
    .join(" · ");

  async function onGenerate(e?: FormEvent) {
    e?.preventDefault();
    setGenerating(true);
    setMessage("");
    try {
      const res = await api.aiTicketDraft(userText);
      setDraft(res.draft);
      setGenerated(res.generated);
    } catch (err: any) {
      setMessage(err.message);
    } finally {
      setGenerating(false);
    }
  }

  async function onCreateFromAi() {
    if (!draft) return;
    setCreating(true);
    setMessage("");
    try {
      const res = await api.createTicket({
        title: draft.title,
        short_description: draft.title,
        description: userText,
        configuration_item: ci || null,
        caller: "admin@example.com",
        sync_servicenow: true,
        use_ai_draft: true,
      });
      setMessage(
        `Created ${res.ticket.number} · ${res.ticket.title || draft.title} · ${res.ticket.priority} · ${
          res.ticket.assignment_group || draft.assignment
        }`
      );
      setDraft(null);
      setGenerated(null);
      await load();
    } catch (err: any) {
      setMessage(err.message);
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>AI Ticket Creation</h1>
        <p>User writes a problem in plain language — AI generates title, category, priority, assignment, SLA, resolution, and KB.</p>
      </header>

      <form className="panel form-grid" onSubmit={onGenerate}>
        <label className="full">
          User writes
          <textarea
            value={userText}
            onChange={(e) => setUserText(e.target.value)}
            required
            rows={3}
            placeholder="My Outlook is not opening after today's update."
          />
        </label>
        <label>
          Configuration item (optional)
          <input value={ci} onChange={(e) => setCi(e.target.value)} placeholder="OUTLOOK-CLIENT" />
        </label>
        <div className="full note-compose-actions">
          <button type="submit" disabled={generating}>
            {generating ? "AI generating…" : "Generate with AI"}
          </button>
          <button type="button" className="ghost" disabled={!draft || creating} onClick={onCreateFromAi}>
            {creating ? "Creating…" : "Create ticket from AI draft"}
          </button>
        </div>
        {message && <p className="full hint">{message}</p>}
      </form>

      {generated && (
        <section className="panel ai-draft-panel">
          <h2>AI generates</h2>
          <dl className="ai-draft-grid">
            {Object.entries(generated).map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
          {draft?.confidence != null && (
            <p className="hint">Confidence {Math.round(draft.confidence * 100)}%</p>
          )}
        </section>
      )}

      <section className="panel">
        <div className="panel-link-header static">
          <h2>Tickets{filterLabel ? ` · ${filtered.length}` : ""}</h2>
          {filterLabel ? (
            <button type="button" className="ghost" onClick={() => setSearchParams({})}>
              Clear filter
            </button>
          ) : null}
        </div>
        {filterLabel && <p className="hint">Filter: {filterLabel}</p>}
        <table className="table">
          <thead>
            <tr>
              <th>Number</th>
              <th>Title</th>
              <th>Priority</th>
              <th>Status</th>
              <th>Assignment</th>
              <th>AI</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((t) => (
              <tr key={t.id} className="clickable-row" onClick={() => navigate(`/tickets/${t.id}`)}>
                <td>
                  <Link to={`/tickets/${t.id}`} onClick={(e) => e.stopPropagation()}>
                    {t.number}
                  </Link>
                </td>
                <td>{t.title || t.short_description}</td>
                <td>
                  <span className={`pill p-${t.priority}`}>{t.priority}</span>
                </td>
                <td>{t.status || t.state}</td>
                <td>{t.assignment_group || t.assigned_to || "—"}</td>
                <td>{Math.round((t.ai_confidence || 0) * 100)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!filtered.length && (
          <p className="hint">{tickets.length ? "No tickets match this filter." : "No tickets yet. Generate an AI draft above."}</p>
        )}
      </section>
    </div>
  );
}
