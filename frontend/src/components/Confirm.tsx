import React, { useEffect } from "react";
import { Button } from "./Button";
import "./Confirm.css";

/**
 * Two confirm tiers §4.7:
 * 1. Inline — button replaced by confirm/cancel in place
 * 2. Modal — destructive, not easily reversible; states specific consequence
 */

export interface InlineConfirmProps {
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
  destructive?: boolean;
}

export function InlineConfirm({
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
  loading,
  destructive,
}: InlineConfirmProps) {
  return (
    <div className="inline-confirm" role="group" aria-label={message}>
      <span className="inline-confirm-msg">{message}</span>
      <div className="inline-confirm-actions">
        <Button size="sm" variant="ghost" onClick={onCancel} disabled={loading}>
          {cancelLabel}
        </Button>
        <Button
          size="sm"
          variant={destructive ? "primary" : "primary"}
          onClick={onConfirm}
          loading={loading}
          className={destructive ? "btn-destructive" : undefined}
        >
          {confirmLabel}
        </Button>
      </div>
    </div>
  );
}

export interface ModalConfirmProps {
  open: boolean;
  title: string;
  consequence: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
  destructive?: boolean;
}

export function ModalConfirm({
  open,
  title,
  consequence,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
  loading,
  destructive = true,
}: ModalConfirmProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div className="modal-scrim" role="presentation" onClick={onCancel}>
      <div
        className="modal-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-confirm-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="modal-confirm-title" className="card-title">
          {title}
        </h2>
        <p className="modal-consequence">{consequence}</p>
        <div className="modal-actions">
          <Button variant="ghost" onClick={onCancel} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button
            variant="primary"
            onClick={onConfirm}
            loading={loading}
            className={destructive ? "btn-destructive" : undefined}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
