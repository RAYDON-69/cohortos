import { cn } from "../lib/utils";

export type AttendanceStatus = "present" | "late" | "absent";
export type PaymentStatus = "locked" | "unpaid" | "due" | "paid";
export type AiStatus =
  | "grounded"
  | "ungrounded"
  | "confidence-low"
  | "confidence-medium"
  | "confidence-high";
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

const VOCAB_CLASS: Record<string, string> = {
  "attendance-present": "bg-sage-100 text-sage-700",
  "attendance-late": "bg-gold-bg text-gold-700",
  "attendance-absent": "bg-error-bg text-error",
  "payment-paid": "bg-sage-100 text-sage-700",
  "payment-due": "bg-gold-bg text-gold-700",
  "payment-unpaid": "bg-error-bg text-error",
  "payment-locked": "bg-slate-500/20 text-slate-700",
  "ai-grounded": "bg-peri-bg text-peri-text",
  "ai-ungrounded": "bg-error-bg text-error",
  "ai-confidence-high": "bg-peri-bg text-peri-text",
  "ai-confidence-medium": "bg-sage-100 text-sage-700",
  "ai-confidence-low": "bg-cream-100 text-slate-700",
  "source-biometric": "bg-sage-100 text-sage-700",
  "source-manual": "bg-cream-100 text-slate-700",
  "source-cross-batch": "bg-gold-bg text-gold-700",
  "source-manual-override": "bg-gold-bg text-gold-700",
  "neutral-neutral": "bg-sage-100 text-sage-700",
  "neutral-info": "bg-peri-bg text-peri-text",
};

export interface BadgeProps {
  kind?: BadgeKind;
  /** Legacy simple variant string */
  variant?: string;
  label?: string;
  children?: React.ReactNode;
  className?: string;
  showDot?: boolean;
}

export function Badge({ kind, variant, label, children, className = "", showDot = false }: BadgeProps) {
  if (kind) {
    const status = kind.status;
    const baseLabel = label ?? LABEL[status] ?? status;
    const key = `${kind.vocab}-${status}`;
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold leading-tight whitespace-nowrap",
          VOCAB_CLASS[key] || "bg-sage-100 text-sage-700",
          className
        )}
        role="status"
      >
        {showDot && <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" aria-hidden />}
        {baseLabel}
      </span>
    );
  }
  const v = variant || "default";
  const map: Record<string, string> = {
    default: "bg-sage-100 text-sage-700",
    "attendance-present": VOCAB_CLASS["attendance-present"],
    "attendance-late": VOCAB_CLASS["attendance-late"],
    "attendance-absent": VOCAB_CLASS["attendance-absent"],
    "payment-paid": VOCAB_CLASS["payment-paid"],
    "payment-due": VOCAB_CLASS["payment-due"],
    "payment-overdue": VOCAB_CLASS["payment-unpaid"],
    "ai-high": VOCAB_CLASS["ai-confidence-high"],
    "ai-medium": VOCAB_CLASS["ai-confidence-medium"],
    "ai-low": VOCAB_CLASS["ai-confidence-low"],
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold leading-tight whitespace-nowrap",
        map[v] || map.default,
        className
      )}
    >
      {children ?? label}
    </span>
  );
}

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

export function PaymentBadge({
  status,
  label,
  showDot = true,
}: {
  status: PaymentStatus;
  label?: string;
  showDot?: boolean;
}) {
  return <Badge kind={{ vocab: "payment", status }} label={label} showDot={showDot} />;
}

export function AiBadge({
  status,
  label,
  showDot = false,
}: {
  status: AiStatus;
  label?: string;
  showDot?: boolean;
}) {
  return <Badge kind={{ vocab: "ai", status }} label={label} showDot={showDot} />;
}


export function SourceBadge({
  status,
  label,
  showDot = false,
}: {
  status: SourceAnnotation;
  label?: string;
  showDot?: boolean;
}) {
  return <Badge kind={{ vocab: "source", status }} label={label} showDot={showDot} />;
}
