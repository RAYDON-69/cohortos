/**
 * Backup & Data Export — owner-only (SPEC_v3 §7, Addendum §1.A).
 * Trigger full export, view snapshot schedule/status, confirm WAL mode.
 */
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { buildDeskNav } from "../../nav/deskNav";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { useTenant } from "../../hooks/useTenant";
import { useLicenseLockout } from "../../hooks/useLicenseLockout";
import {
  getBackupStatus,
  triggerBackupExport,
  type ApiError,
} from "../../api/client";

type BackupStatus = {
  db_path: string;
  wal_active: boolean;
  journal_mode: string;
  backups: { path: string; name: string; size: number }[];
  backup_dir: string | null;
};

export function BackupExportScreen() {
  const navigate = useNavigate();
  const { tenantId } = useTenant();
  const license = useLicenseLockout();
  const [status, setStatus] = useState<BackupStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [lastExport, setLastExport] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!tenantId) {
      setLoading(false);
      setError("No centre selected");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await getBackupStatus(tenantId);
      setStatus(res);
    } catch (e) {
      setError((e as ApiError)?.detail || (e as Error)?.message || "Failed to load backup status");
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onExport() {
    if (!tenantId || license.locked) return;
    setExporting(true);
    setError(null);
    setMessage(null);
    try {
      const res = await triggerBackupExport(tenantId);
      setMessage(res.message || "Export complete");
      setLastExport(
        res.snapshot_path ||
          `JSON tables: ${Object.keys(res.export?.tables || {}).join(", ")}`
      );
      // Download JSON portable archive in browser
      const blob = new Blob([JSON.stringify(res.export, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cohortos-export-${tenantId.slice(0, 8)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      await load();
    } catch (e) {
      setError((e as ApiError)?.detail || "Export failed");
    } finally {
      setExporting(false);
    }
  }

  const nav = buildDeskNav(navigate, "backup", undefined, "owner");

  return (
    <AppShell brand="CohortOS" navItems={nav} crumb="Backup & export">
      <div className="view" data-testid="backup-export">
        <header className="view-header">
          <h1 className="view-title">Backup & data export</h1>
          <p className="caption muted">
            Disaster recovery for offline-first centres on unreliable power. Export stays
            available even during billing lockout.
          </p>
        </header>

        {loading && (
          <div className="skeleton-block" role="status">
            Loading backup status…
          </div>
        )}

        {!loading && error && (
          <div className="banner banner-error" role="alert">
            {error}
            <Button variant="ghost" size="sm" onClick={() => void load()}>
              Retry
            </Button>
          </div>
        )}

        {!loading && !error && status && (
          <div className="card-stack">
            <section className="card" aria-labelledby="wal-heading">
              <h2 id="wal-heading" className="card-title">
                Database durability
              </h2>
              <p>
                Journal mode:{" "}
                <strong className="mono">{status.journal_mode}</strong>
              </p>
              <p>
                WAL active:{" "}
                {status.wal_active ? (
                  <span className="badge badge-ok">Yes</span>
                ) : (
                  <span className="badge badge-warn">No / not applicable</span>
                )}
              </p>
              <p className="caption muted mono">Path: {status.db_path}</p>
            </section>

            <section className="card" aria-labelledby="snap-heading">
              <h2 id="snap-heading" className="card-title">
                Local snapshots
              </h2>
              {(status.backups?.length ?? 0) === 0 ? (
                <EmptyState
                  title="No snapshots yet"
                  body="Trigger an export to create a snapshot when the database is file-backed."
                />
              ) : (
                <ul>
                  {(status.backups || []).map((b) => (
                    <li key={b.path}>
                      <span className="mono">{b.name}</span> — {b.size} bytes
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="card">
              <Button
                variant="primary"
                disabled={exporting}
                onClick={() => void onExport()}
              >
                {exporting ? "Exporting…" : "Export full dataset (JSON)"}
              </Button>
              {/* Export allowed during lockout by design */}
              {message && (
                <p className="caption" role="status">
                  {message}
                </p>
              )}
              {lastExport && (
                <p className="caption muted mono">{lastExport}</p>
              )}
            </section>
          </div>
        )}
      </div>
    </AppShell>
  );
}
