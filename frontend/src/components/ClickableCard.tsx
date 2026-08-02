import { Link } from "react-router-dom";
import type { ReactNode } from "react";

type Props = {
  to: string;
  className?: string;
  children: ReactNode;
  title?: string;
};

/** Link-styled card used across dashboards, architecture, and workflow tiles. */
export default function ClickableCard({ to, className = "", children, title }: Props) {
  return (
    <Link to={to} className={`clickable-card ${className}`.trim()} title={title || "Open"}>
      {children}
    </Link>
  );
}
