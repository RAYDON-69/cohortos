import { cn } from "../lib/utils";
import { useConnectivity } from "../hooks/useConnectivity";

export function SyncPill({ onConflictClick }: { onConflictClick?: () => void }) {
  const { state } = useConnectivity();
  const label =
    state === "offline"
      ? "Offline"
      : state === "syncing"
        ? "Syncing…"
        : state === "conflict"
          ? "Conflicts"
          : "Synced";
  const dot =
    state === "offline"
      ? "bg-slate-500"
      : state === "conflict"
        ? "bg-error"
        : state === "syncing"
          ? "bg-gold-500"
          : "bg-sage-500";
  return (
    <button
      type="button"
      className="inline-flex items-center gap-1.5 rounded-full border border-border bg-white px-2.5 py-1 text-[11px] font-semibold text-ink"
      onClick={state === "conflict" ? onConflictClick : undefined}
      title={label}
    >
      <span className={cn("h-2 w-2 rounded-full", dot)} aria-hidden />
      {label}
    </button>
  );
}
