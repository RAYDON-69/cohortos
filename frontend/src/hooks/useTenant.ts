import { useMemo } from "react";
import { loadTokens } from "../api/client";

/**
 * Current tenant_id, centre name (when available), and mode placeholder.
 * Screens should prefer this over scattered loadTokens() calls.
 */
export function useTenant() {
  const tokens = loadTokens();
  return useMemo(
    () => ({
      tenantId: tokens.tenant_id || "",
      accountId: tokens.account_id || "",
      // centre name / mode filled when /me or settings endpoints are wired into context
      centreName: "",
      mode: "offline-first" as "offline-first" | "cloud-first" | "hybrid",
    }),
    [tokens.tenant_id, tokens.account_id]
  );
}
