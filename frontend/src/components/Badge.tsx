import { cn } from "../lib/utils";

type Props = {
  children: React.ReactNode;
  variant?:
    | "attendance-present"
    | "attendance-late"
    | "attendance-absent"
    | "payment-paid"
    | "payment-due"
    | "payment-overdue"
    | "ai-high"
    | "ai-medium"
    | "ai-low"
    | "default";
  className?: string;
};

const variants: Record<string, string> = {
  "attendance-present": "bg-sage-100 text-sage-700",
  "attendance-late": "bg-gold-bg text-gold-700",
  "attendance-absent": "bg-error-bg text-error",
  "payment-paid": "bg-sage-100 text-sage-700",
  "payment-due": "bg-gold-bg text-gold-700",
  "payment-overdue": "bg-error-bg text-error",
  "ai-high": "bg-peri-bg text-peri-text",
  "ai-medium": "bg-sage-100 text-sage-700",
  "ai-low": "bg-cream-100 text-slate-700",
  default: "bg-sage-100 text-sage-700",
};

export function Badge({ children, variant = "default", className }: Props) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold leading-tight whitespace-nowrap",
        variants[variant] || variants.default,
        className
      )}
    >
      {children}
    </span>
  );
}
