import { useEffect, useMemo, useState } from "react";

type Props = {
  content: string;
  /** Map of /api/... attachment paths → data URLs or blob URLs */
  imageMap?: Record<string, string>;
};

function authToken(): string | null {
  return localStorage.getItem("token");
}

function Inline({ text, imageMap }: { text: string; imageMap?: Record<string, string> }) {
  // Split images, links, code, bold, italic
  const parts = text.split(/(!\[[^\]]*\]\([^)]+\)|\[[^\]]+\]\([^)]+\)|`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g);
  return (
    <>
      {parts.map((part, i) => {
        const img = part.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
        if (img) {
          const src = imageMap?.[img[2]] || img[2];
          return <AuthImage key={i} src={src} alt={img[1]} original={img[2]} imageMap={imageMap} />;
        }
        const link = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
        if (link) {
          return (
            <a key={i} href={link[2]} target="_blank" rel="noreferrer">
              {link[1]}
            </a>
          );
        }
        const code = part.match(/^`([^`]+)`$/);
        if (code) return <code key={i}>{code[1]}</code>;
        const bold = part.match(/^\*\*([^*]+)\*\*$/);
        if (bold) return <strong key={i}>{bold[1]}</strong>;
        const italic = part.match(/^\*([^*]+)\*$/);
        if (italic) return <em key={i}>{italic[1]}</em>;
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}

function AuthImage({
  src,
  alt,
  original,
  imageMap,
}: {
  src: string;
  alt: string;
  original: string;
  imageMap?: Record<string, string>;
}) {
  const [resolved, setResolved] = useState(imageMap?.[original] || src);

  useEffect(() => {
    if (imageMap?.[original]) {
      setResolved(imageMap[original]);
      return;
    }
    if (!original.startsWith("/api/")) return;
    const token = authToken();
    if (!token) return;
    let objectUrl = "";
    fetch(original, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.blob() : Promise.reject()))
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setResolved(objectUrl);
      })
      .catch(() => undefined);
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [original, imageMap]);

  return <img className="md-image" src={resolved} alt={alt || "attachment"} />;
}

export default function MarkdownView({ content, imageMap }: Props) {
  const blocks = useMemo(() => content.replace(/\r\n/g, "\n").split(/\n{2,}/), [content]);

  return (
    <div className="md-view">
      {blocks.map((block, idx) => {
        const trimmed = block.trim();
        if (!trimmed) return null;
        if (trimmed.startsWith("```")) {
          const body = trimmed.replace(/^```\w*\n?/, "").replace(/\n?```$/, "");
          return (
            <pre key={idx} className="md-codeblock">
              <code>{body}</code>
            </pre>
          );
        }
        if (/^#{1,3}\s/.test(trimmed)) {
          const level = trimmed.match(/^(#{1,3})\s/)?.[1].length || 1;
          const text = trimmed.replace(/^#{1,3}\s/, "");
          const Tag = (`h${Math.min(level + 2, 5)}` as "h3" | "h4" | "h5");
          return (
            <Tag key={idx}>
              <Inline text={text} imageMap={imageMap} />
            </Tag>
          );
        }
        if (/^[-*]\s/m.test(trimmed) && trimmed.split("\n").every((l) => /^[-*]\s/.test(l) || !l.trim())) {
          return (
            <ul key={idx}>
              {trimmed.split("\n").map((line, i) => (
                <li key={i}>
                  <Inline text={line.replace(/^[-*]\s/, "")} imageMap={imageMap} />
                </li>
              ))}
            </ul>
          );
        }
        return (
          <p key={idx}>
            {trimmed.split("\n").map((line, i) => (
              <span key={i}>
                {i > 0 && <br />}
                <Inline text={line} imageMap={imageMap} />
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}
