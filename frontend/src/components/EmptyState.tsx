import React from "react";
import "./EmptyState.css";

/**
 * Empty states §4.9 — specific, non-generic; invitation to act.
 */

export interface EmptyStateProps {
  mark?: React.ReactNode;
  title: string;
  body?: string;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({
  mark = "·",
  title,
  body,
  action,
  className = "",
}: EmptyStateProps) {
  return (
    <div className={`empty-state ${className}`} role="status">
      <div className="empty-mark" aria-hidden="true">
        {mark}
      </div>
      <div className="empty-title">{title}</div>
      {body && <div className="empty-body">{body}</div>}
      {action && <div className="empty-action">{action}</div>}
    </div>
  );
}
