import React, { useEffect, useState } from "react";
import { getSyncState, setSyncStateListener } from "../api/client"
import type { SyncState } from "../api/client"
import { useLocale } from "../i18n/LocaleContext";
import "./OfflineBanner.css";

/**
 * Offline banner — Portion 24
 * Surfaces connectivity pill's Offline state as a non-blocking banner so
 * mid-flow network loss never looks like a broken/loading screen (§0).
 */
export function OfflineBanner() {
  const { t } = useLocale();
  const [state, setState] = useState<SyncState>(() => getSyncState());

  useEffect(() => {
    return setSyncStateListener(setState);
  }, []);

  if (state !== "offline") return null;

  return (
    <div className="offline-banner" role="status" aria-live="polite">
      <strong>{t("syncOffline")}</strong>
      <span className="caption">{t("offlineBannerBody")}</span>
    </div>
  );
}
