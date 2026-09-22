import { cn } from "../lib/utils";

export function EmptyState({
  title = "Nothing here yet",
  body,
  action,
  className,
}: {
  title?: string;
  body?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-card border border-dashed border-border bg-white px-4 py-10 text-center text-slate-700",
        className
      )}
    >
      <div className="text-2xl text-sage-300" aria-hidden>
        ···
      </div>
      <div className="mt-2 text-sm font-semibold text-ink">{title}</div>
      {body && <div className="mt-1 text-sm">{body}</div>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
