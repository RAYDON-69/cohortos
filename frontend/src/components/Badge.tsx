import "./Badge.css";

/**
 * Status badges — three independent vocabularies (status-vocabulary-integrity).
 * Never color-only: always label (+ optional icon).
 * §4.2
 */

export type AttendanceStatus = "present" | "late" | "absent";
export type PaymentStatus = "locked" | "unpaid" | "due" | "paid";
export type AiStatus = "grounded" | "ungrounded" | "confidence-low" | "confidence-medium" | "confidence-high";
export type SourceAnnotation = "biometric" | "manual" | "cross-batch" | "manual-override";
export type NeutralBadge = "neutral" | "info";

export type BadgeKind =
  | { vocab: "attendance"; status: AttendanceStatus }
  | { vocab: "payment"; status: PaymentStatus }
  | { vocab: "ai"; status: AiStatus }
  | { vocab: "source"; status: SourceAnnotation }
  | { vocab: "neutral"; status: NeutralBadge };

const LABEL: Record<string, string> = {
  present: "Present",
  late: "Late",
  absent: "Absent",
  locked: "Locked",
  unpaid: "Unpaid",
  due: "Due",
  paid: "Paid",
  grounded: "Grounded",
  ungrounded: "Ungrounded",
  "confidence-low": "Low confidence",
  "confidence-medium": "Medium",
  "confidence-high": "High",
  biometric: "Biometric",
  manual: "Manual",
  "cross-batch": "Cross-batch",
  "manual-override": "Manual override",
  neutral: "",
  info: "Info",
};

export interface BadgeProps {
  kind: BadgeKind;
  /** Override label (e.g. i18n) */
  label?: string;
  className?: string;
  /** Show status dot (gold-500 for late only, etc.) */
  showDot?: boolean;
}

export function Badge({ kind, label, className = "", showDot = false }: BadgeProps) {
  const status = kind.status;
  const baseLabel = label ?? LABEL[status] ?? status;
  const classes = ["badge", `badge-${kind.vocab}-${status}`, className].filter(Boolean).join(" ");

  return (
    <span className={classes} role="status">
      {showDot && <span className={`badge-dot badge-dot-${status}`} aria-hidden="true" />}
      {baseLabel}
    </span>
  );
}

/** Convenience helpers that keep vocabularies distinct */
export function AttendanceBadge({
  status,
  label,
  showDot = true,
}: {
  status: AttendanceStatus;
  label?: string;
  showDot?: boolean;
}) {
  return <Badge kind={{ vocab: "attendance", status }} label={label} showDot={showDot} />;
}

export function PaymentBadge({ status, label, showDot = true }: { status: PaymentStatus; label?: string; showDot?: boolean }) {
  return <Badge kind={{ vocab: "payment", status }} label={label} showDot={showDot} />;
}

export function AiBadge({ status, label }: { status: AiStatus; label?: string }) {
  return <Badge kind={{ vocab: "ai", status }} label={label} />;
}

export function SourceBadge({ status, label }: { status: SourceAnnotation; label?: string }) {
  return <Badge kind={{ vocab: "source", status }} label={label} />;
}
