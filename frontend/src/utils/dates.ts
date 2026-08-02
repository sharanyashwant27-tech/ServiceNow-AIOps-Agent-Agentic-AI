/** Format ISO timestamps for ticket lists and detail views. */

/** Parse API datetimes; treat naive ISO values as UTC (matches backend). */
export function parseApiDate(value?: string | Date | null): Date | null {
  if (!value) return null;
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }
  const raw = String(value).trim();
  if (!raw) return null;
  const normalized = /[zZ]|[+-]\d{2}:?\d{2}$/.test(raw) ? raw : `${raw}Z`;
  const d = new Date(normalized);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatDate(value?: string | Date | null, fallback = "—"): string {
  const d = parseApiDate(value);
  if (!d) return fallback;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDateShort(value?: string | Date | null, fallback = "—"): string {
  const d = parseApiDate(value);
  if (!d) return fallback;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/** Same calendar day in UTC — aligns with dashboard "Resolved Today" counting. */
export function isUtcToday(value?: string | Date | null, ref: Date = new Date()): boolean {
  const d = parseApiDate(value);
  if (!d) return false;
  return (
    d.getUTCFullYear() === ref.getUTCFullYear() &&
    d.getUTCMonth() === ref.getUTCMonth() &&
    d.getUTCDate() === ref.getUTCDate()
  );
}

export function ticketCompletedAt(t: {
  completed_date?: string | null;
  closed_at?: string | null;
  resolved_at?: string | null;
}): string | null {
  return t.completed_date || t.closed_at || t.resolved_at || null;
}

export function ticketResolvedAt(t: {
  completed_date?: string | null;
  completed_date_iso?: string | null;
  closed_at?: string | null;
  closed_at_iso?: string | null;
  resolved_at?: string | null;
  resolved_at_iso?: string | null;
  updated_at?: string | null;
}): string | null {
  return (
    t.resolved_at_iso ||
    t.resolved_at ||
    t.closed_at_iso ||
    t.closed_at ||
    t.completed_date_iso ||
    t.completed_date ||
    t.updated_at ||
    null
  );
}

export function ticketCreatedAt(t: {
  created_date?: string | null;
  created_at?: string | null;
}): string | null {
  return t.created_date || t.created_at || null;
}

export function ticketAssignment(t: {
  assignment?: string | null;
  assigned_to?: string | null;
  assignment_group?: string | null;
}): string {
  if (t.assignment) return t.assignment;
  if (t.assigned_to && t.assignment_group) return `${t.assigned_to} · ${t.assignment_group}`;
  return t.assigned_to || t.assignment_group || "Unassigned";
}

export function ticketStatus(t: { status?: string | null; state?: string | null }): string {
  return t.status || t.state || "—";
}
