/**
 * App-wide license / billing lockout (SPEC_v3 §0, Addendum §1.A).
 * When billing is delinquent past grace, app is read-only:
 * data visible/exportable; all write actions disabled with billing message.
 */
import { useCallback, useEffect, useState } from "react";
import { loadTokens, apiRequest, tenantPath } from "../api/client";

export type LicenseStatus = {
  locked: boolean;
  reason: string | null;
  graceEndsAt: string | null;
  loading: boolean;
};

export function useLicenseLockout(): LicenseStatus & { refresh: () => Promise<void> } {
  const [locked, setLocked] = useState(false);
  const [reason, setReason] = useState<string | null>(null);
  const [graceEndsAt, setGraceEndsAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const tokens = loadTokens();
      const tid = tokens.tenant_id;
      if (!tid) {
        setLocked(false);
        setReason(null);
        return;
      }
      const res = await apiRequest<{
        locked?: boolean;
        reason?: string;
        grace_ends_at?: string | null;
        status?: string;
      }>(tenantPath(tid, "/license/status"));
      const isLocked =
        Boolean(res.locked) ||
        res.status === "delinquent" ||
        res.status === "lockout";
      setLocked(isLocked);
      setReason(
        isLocked
          ? res.reason ||
              "Billing is past the grace window. The desk is read-only until payment is settled."
          : null
      );
      setGraceEndsAt(res.grace_ends_at ?? null);
    } catch {
      // Offline or route missing: do not lock the app
      setLocked(false);
      setReason(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { locked, reason, graceEndsAt, loading, refresh };
}
