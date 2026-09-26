import { useSyncExternalStore } from "react";
import { loadTokens, onTokenChange } from "../api/client";

/**
 * Current tenant_id, centre name (when available), and mode placeholder.
 * Screens should prefer this over scattered loadTokens() calls.
 *
 * Subscribes to token changes so that after ensureSession / saveTokens
 * (module-level memory + localStorage) consumers re-render with the new
 * tenant_id instead of showing "No centre selected".
 */
function getTenantSnapshot(): string {
  const t = loadTokens();
  return `${t.tenant_id || ""}|${t.account_id || ""}`;
}

export function useTenant() {
  const snap = useSyncExternalStore(onTokenChange, getTenantSnapshot, getTenantSnapshot);
  const [tenantId, accountId] = snap.split("|");
  return {
    tenantId: tenantId || "",
    accountId: accountId || "",
    centreName: "",
    mode: "offline-first" as "offline-first" | "cloud-first" | "hybrid",
  };
}
