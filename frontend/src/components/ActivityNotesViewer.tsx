import MarkdownView from "./MarkdownView";

async function openAuthenticated(url?: string, filename?: string) {
  if (!url) return;
  const token = localStorage.getItem("token");
  const res = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("Download failed");
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename || "attachment";
  a.target = "_blank";
  a.click();
  URL.revokeObjectURL(objectUrl);
}

type ActivityNote = {
  id?: string;
  date: string;
  text: string;
  author?: string;
  format?: string;
};

type Attachment = {
  id: string;
  filename: string;
  content_type?: string;
  size_bytes?: number;
  is_image?: boolean;
  download_url?: string;
  preview_data_url?: string;
};

type Support = { id: string; title: string; description?: string };

type Props = {
  notes: ActivityNote[];
  viewerText?: string;
  aiSummary?: string;
  attachments?: Attachment[];
  images?: Attachment[];
  supports?: Support[];
  onRefreshSummary?: () => void;
  refreshingSummary?: boolean;
};

export default function ActivityNotesViewer({
  notes,
  viewerText,
  aiSummary,
  attachments = [],
  images = [],
  supports = [],
  onRefreshSummary,
  refreshingSummary,
}: Props) {
  const imageMap: Record<string, string> = {};
  for (const img of images) {
    if (img.preview_data_url && img.download_url) {
      imageMap[img.download_url] = img.preview_data_url;
    }
  }

  const defaultSupports: Support[] = [
    { id: "markdown", title: "Markdown" },
    { id: "images", title: "Images" },
    { id: "attachments", title: "Attachments" },
    { id: "ai_summary", title: "AI Summary" },
  ];
  const caps = supports.length ? supports : defaultSupports;

  return (
    <div className="activity-viewer" aria-label="Activity Notes Viewer">
      <div className="activity-viewer-label">Activity Notes</div>
      <div className="notes-supports">
        {caps.map((s) => (
          <span key={s.id} className="support-chip" title={s.description || s.title}>
            {s.title}
          </span>
        ))}
      </div>

      {aiSummary ? (
        <section className="ai-summary-card">
          <div className="ai-summary-head">
            <strong>AI Summary</strong>
            {onRefreshSummary && (
              <button type="button" className="ghost" onClick={onRefreshSummary} disabled={refreshingSummary}>
                {refreshingSummary ? "Refreshing…" : "Refresh"}
              </button>
            )}
          </div>
          <MarkdownView content={aiSummary} imageMap={imageMap} />
        </section>
      ) : (
        onRefreshSummary && (
          <button type="button" className="ghost" onClick={onRefreshSummary} disabled={refreshingSummary}>
            Generate AI Summary
          </button>
        )
      )}

      {!notes?.length ? (
        <p className="hint">No activity notes yet.</p>
      ) : (
        notes.map((note, idx) => (
          <div key={note.id || `${note.date}-${idx}`} className="activity-entry">
            <div className="activity-date">{note.date}</div>
            <div className="activity-text">
              {note.format === "markdown" || note.format === undefined ? (
                <MarkdownView content={note.text} imageMap={imageMap} />
              ) : (
                note.text
              )}
            </div>
            {idx < notes.length - 1 && <div className="activity-divider">-------------------</div>}
          </div>
        ))
      )}

      {!!images.length && (
        <section className="notes-media">
          <h3>Images</h3>
          <div className="image-grid">
            {images.map((img) => (
              <button
                key={img.id}
                type="button"
                className="image-tile"
                onClick={() => openAuthenticated(img.download_url, img.filename).catch(console.error)}
              >
                {img.preview_data_url ? (
                  <img src={img.preview_data_url} alt={img.filename} />
                ) : (
                  <span>{img.filename}</span>
                )}
              </button>
            ))}
          </div>
        </section>
      )}

      {!!attachments.length && (
        <section className="notes-media">
          <h3>Attachments</h3>
          <ul className="attachment-list">
            {attachments.map((att) => (
              <li key={att.id}>
                <button
                  type="button"
                  className="linkish"
                  onClick={() => openAuthenticated(att.download_url, att.filename).catch(console.error)}
                >
                  {att.filename}
                </button>
                <span>
                  {att.content_type} · {Math.round((att.size_bytes || 0) / 1024)} KB
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {viewerText ? (
        <details className="activity-raw">
          <summary>Plain-text viewer</summary>
          <pre>{viewerText}</pre>
        </details>
      ) : null}
    </div>
  );
}
