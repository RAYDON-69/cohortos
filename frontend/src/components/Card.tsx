import { cn } from "../lib/utils";
export {
  Card as UiCard,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "./ui/card";

type Props = React.HTMLAttributes<HTMLDivElement> & {
  variant?: string;
  title?: string;
  eyebrow?: string;
};

export function Card({ className, variant, title, eyebrow, children, ...props }: Props) {
  return (
    <div
      className={cn(
        "rounded-card border border-border bg-white p-6 shadow-soft text-left",
        variant === "muted" && "bg-sage-100/50",
        variant === "outline" && "shadow-none",
        className
      )}
      {...props}
    >
      {eyebrow && <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-sage-700">{eyebrow}</p>}
      {title && <h3 className="mb-2 font-semibold text-ink">{title}</h3>}
      {children}
    </div>
  );
}
