/**
 * Sync Conflict Log — owner-only (SPEC_v3 §7, Addendum §1.A).
 * Lists sync conflicts especially locked-payment records excluded from LWW.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { buildDeskNav } from "../../nav/deskNav";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { DataTable, type Column } from "../../components/DataTable";
import { PaymentBadge } from "../../components/Badge";
import { useTenant } from "../../hooks/useTenant";
import { useLicenseLockout } from "../../hooks/useLicenseLockout";
import {
  listSyncConflicts,
  resolveSyncConflict,
  type SyncConflictRow,
  type ApiError,
} from "../../api/client";

export function ConflictLogScreen() {
  const navigate = useNavigate();
  const { tenantId } = useTenant();
  const license = useLicenseLockout();
  const [rows, setRows] = useState<SyncConflictRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resolving, setResolving] = useState<number | null>(null);

  const load = useCallback(async () => {
    if (!tenantId) {
      setLoading(false);
      setError("No centre selected");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await listSyncConflicts(tenantId);
      setRows(res.conflicts || []);
    } catch (e) {
      setError((e as ApiError)?.detail || (e as Error)?.message || "Failed to load conflicts");
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onResolve(id: number, resolution: string) {
    if (license.locked) return;
    setResolving(id);
    try {
      await resolveSyncConflict(tenantId, id, resolution);
      await load();
    } catch (e) {
      setError((e as ApiError)?.detail || "Resolve failed");
    } finally {
      setResolving(null);
    }
  }

  const columns: Column<SyncConflictRow>[] = useMemo(
    () => [
      {
        key: "table_name",
        header: "Table",
        essential: true,
        sortable: true,
        render: (r) => r.table_name || "—",
      },
      {
        key: "record_id",
        header: "Record",
        essential: true,
        render: (r) => <span className="mono-data">{r.record_id}</span>,
      },
      {
        key: "field_name",
        header: "Field",
        render: (r) => r.field_name || "—",
      },
      {
        key: "local_value",
        header: "Local",
        render: (r) => <span className="mono-data">{String(r.local_value ?? "—")}</span>,
      },
      {
        key: "remote_value",
        header: "Remote",
        render: (r) => <span className="mono-data">{String(r.remote_value ?? "—")}</span>,
      },
      {
        key: "flags",
        header: "Flags",
        essential: true,
        render: (r) =>
          r.is_locked_payment ? (
            <PaymentBadge status="locked" label="Locked payment" />
          ) : (
            <span className="caption muted">—</span>
          ),
      },
      {
        key: "actions",
        header: "Actions",
        essential: true,
        render: (r) => (
          <span style={{ display: "inline-flex", gap: 8, flexWrap: "wrap" }}>
            <Button
              variant="outline"
              size="sm"
              disabled={license.locked || resolving === r.id}
              loading={resolving === r.id}
              onClick={() => r.id != null && void onResolve(Number(r.id), "local")}
            >
              Keep local
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled={license.locked || resolving === r.id}
              onClick={() => r.id != null && void onResolve(Number(r.id), "remote")}
            >
              Take remote
            </Button>
          </span>
        ),
      },
    ],
    [license.locked, resolving, tenantId]
  );

  const nav = buildDeskNav(navigate, "conflicts", undefined, "owner");

  return (
    <AppShell brand="CohortOS" navItems={nav} crumb="Sync conflicts">
      <div className="view" data-testid="conflict-log">
        <header className="view-header">
          <h1 className="view-title">Sync conflict log</h1>
          <p className="caption muted">
            Locked payment records never auto-resolve (last-write-wins). Resolve them here.
          </p>
          <Button variant="outline" onClick={() => void load()} disabled={loading}>
            Refresh
          </Button>
        </header>

        {loading && (
          <DataTable
            columns={columns}
            rows={[]}
            rowKey={(r) => String(r.id)}
            loading
            emptyTitle="Loading conflicts…"
          />
        )}

        {!loading && error && (
          <div className="warning-banner" role="alert">
            {error}
            <Button variant="ghost" size="sm" onClick={() => void load()}>
              Retry
            </Button>
          </div>
        )}

        {!loading && !error && rows.length === 0 && (
          <EmptyState
            title="No open conflicts"
            body="Sync is clean. Locked-payment disagreements will appear here instead of overwriting each other."
          />
        )}

        {!loading && !error && rows.length > 0 && (
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(r) => String(r.id ?? `${r.table_name}-${r.record_id}`)}
            emptyTitle="No open conflicts"
          />
        )}
      </div>
    </AppShell>
  );
}
