/**
 * Batch detail — roster, schedule, per-student fee status (dedicated screen).
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { buildDeskNav } from "../../nav/deskNav";
import { Card } from "../../components/Card";
import { useTenant } from "../../hooks/useTenant";
import { apiRequest, tenantPath, type ApiError } from "../../api/client";
import "../../components/Card.css";
import "../../shell/AppShell.css";

export function BatchDetailScreen() {
  const { batchId } = useParams<{ batchId: string }>();
  const navigate = useNavigate();
  const { tenantId } = useTenant();
  const [batch, setBatch] = useState<Record<string, unknown> | null>(null);
  const [students, setStudents] = useState<Record<string, unknown>[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!tenantId || !batchId) return;
    setLoading(true);
    setError(null);
    try {
      const [bl, st] = await Promise.all([
        apiRequest<{ batches?: Record<string, unknown>[] }>(tenantPath(tenantId, "/batches")),
        apiRequest<{ students?: Record<string, unknown>[] }>(tenantPath(tenantId, "/students")).catch(() => ({ students: [] })),
      ]);
      const b = (bl.batches || []).find((x) => String(x.id) === batchId) || null;
      setBatch(b);
      setStudents((st.students || []).filter((s) => String(s.batch_id) === batchId));
    } catch (e) {
      setError((e as ApiError)?.detail || "Could not load batch");
    } finally {
      setLoading(false);
    }
  }, [tenantId, batchId]);

  useEffect(() => {
    void load();
  }, [load]);

  const nav = buildDeskNav(navigate, "batches");
  const name = String(batch?.name || batchId || "Batch");

  return (
    <AppShell brand="CohortOS" navItems={nav} crumb={`Batch · ${name}`}>
      <div className="view" data-testid="batch-detail">
        <h1 className="view-title">{name}</h1>
        {loading && <p className="caption muted">Loading…</p>}
        {error && <p className="error-text" role="alert">{error}</p>}
        {batch && (
          <Card title="Schedule">
            <p className="caption">
              Days: {Array.isArray(batch.days) ? (batch.days as string[]).join(", ") : "—"} · Hour:{" "}
              {String(batch.hour ?? "—")}
            </p>
          </Card>
        )}
        <Card title="Roster" style={{ marginTop: 16 }}>
          {students.length === 0 ? (
            <p className="caption muted">No students in this batch yet.</p>
          ) : (
            <ul>
              {students.map((s) => (
                <li key={String(s.id)}>
                  <Link to={`/students/${s.id}`}>{String(s.name || s.id)}</Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Fees" style={{ marginTop: 16 }}>
          <p className="caption muted">Open Fees this month for per-student paid / due status for this batch.</p>
        </Card>
      </div>
    </AppShell>
  );
}
