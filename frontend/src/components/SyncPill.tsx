import React, { useEffect, useState } from "react";
import { getSyncState, getLastSyncedAt, setSyncStateListener } from "../api/client"
import type { SyncState } from "../api/client"
import { useLocale } from "../i18n/LocaleContext";
import "./SyncPill.css";

/**
 * Connectivity/sync pill — signature element §4.4 / offline-first-ux-states.
 * Always visible. Four states exactly. Offline is neutral, never error-styled.
 */

function formatRelative(ms: number | null, t: (k: any, v?: any) => string): string {
  if (ms == null) return t("justNow");
  const diff = Math.max(0, Date.now() - ms);
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return t("justNow");
  if (mins < 60) return t("minutesAgo", { n: mins });
  const hours = Math.floor(mins / 60);
  return t("hoursAgo", { n: hours });
}

export interface SyncPillProps {
  onConflictClick?: () => void;
  className?: string;
}

export function SyncPill({ onConflictClick, className = "" }: SyncPillProps) {
  const { t } = useLocale();
  const [state, setState] = useState<SyncState>(getSyncState);
  const [relative, setRelative] = useState(() => formatRelative(getLastSyncedAt(), t));

  useEffect(() => {
    setSyncStateListener(setState);
  }, []);

  useEffect(() => {
    if (state !== "synced") return;
    const tick = () => setRelative(formatRelative(getLastSyncedAt(), t));
    tick();
    const id = setInterval(tick, 15000);
    return () => clearInterval(id);
  }, [state, t]);

  const label =
    state === "offline"
      ? t("syncOffline")
      : state === "syncing"
        ? t("syncSyncing")
        : state === "conflict"
          ? t("syncConflict")
          : t("syncSynced", { time: relative });

  const isClickable = state === "conflict" && onConflictClick;

  return (
    <button
      type="button"
      className={`sync-pill sync-pill-${state} ${className}`}
      onClick={isClickable ? onConflictClick : undefined}
      disabled={!isClickable}
      aria-live="polite"
      aria-label={label}
    >
      <span className={`sync-dot sync-dot-${state}`} aria-hidden="true" />
      <span className="sync-label">{label}</span>
    </button>
  );
}
