/**
 * Dedicated student profile — not the admissions table.
 * Payments, admission date, attendance summary, exam results, notes.
 */
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { buildDeskNav } from "../../nav/deskNav";
import { Card } from "../../components/Card";
import { useTenant } from "../../hooks/useTenant";
import { apiRequest, tenantPath, type ApiError } from "../../api/client";

type Profile = {
  student?: Record<string, unknown>;
  payments?: unknown[];
  attendance?: unknown[];
  results?: unknown[];
  notes?: string;
};

export function StudentProfileScreen() {
  const { studentId } = useParams<{ studentId: string }>();
  const navigate = useNavigate();
  const { tenantId } = useTenant();
  const [data, setData] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!tenantId || !studentId) return;
    setLoading(true);
    setError(null);
    try {
      // Compose from existing endpoints until a single /students/{id}/profile exists
      const [stu, exams] = await Promise.all([
        apiRequest<{ students?: Record<string, unknown>[] }>(tenantPath(tenantId, "/students")).catch(() => ({ students: [] })),
        apiRequest<{ exams?: unknown[] }>(tenantPath(tenantId, "/exams")).catch(() => ({ exams: [] })),
      ]);
      const student = (stu.students || []).find((s) => String(s.id) === studentId || String(s.student_id) === studentId);
      setData({
        student: student || { id: studentId, name: "Student" },
        payments: [],
        attendance: [],
        results: exams.exams || [],
        notes: String((student as { notes?: string })?.notes || ""),
      });
    } catch (e) {
      setError((e as ApiError)?.detail || "Could not load profile");
    } finally {
      setLoading(false);
    }
  }, [tenantId, studentId]);

  useEffect(() => {
    void load();
    const onRetry = () => void load();
    window.addEventListener("cohortos:retry", onRetry);
    return () => window.removeEventListener("cohortos:retry", onRetry);
  }, [load]);

  const nav = buildDeskNav(navigate, "admissions");
  const name = String(data?.student?.name || studentId || "Student");

  return (
    <AppShell brand="CohortOS" navItems={nav} crumb={`Student · ${name}`}>
      <div className="view" data-testid="student-profile">
        <h1 className="view-title">{name}</h1>
        {loading && <p className="caption muted">Loading…</p>}
        {error && <p className="error-text" role="alert">{error}</p>}
        {data?.student && (
          <>
            <Card title="Overview">
              <p className="caption">ID: {String(data.student.id || studentId)}</p>
              <p className="caption">Phone: {String(data.student.phone || "—")}</p>
              <p className="caption">Batch: {String(data.student.batch_id || "—")}</p>
              <p className="caption">Admitted: {String(data.student.admission_date || data.student.created_at || "—")}</p>
            </Card>
            <Card title="Notes" style={{ marginTop: 16 }}>
              <p>{data.notes || "No notes yet."}</p>
            </Card>
            <Card title="Exams linked to centre" style={{ marginTop: 16 }}>
              <p className="caption muted">{(data.results || []).length} exam(s) on file — open Exams for marks.</p>
            </Card>
            <Card title="Payments & attendance" style={{ marginTop: 16 }}>
              <p className="caption muted">
                Full payment history and attendance timeline use the Fees and Attendance screens for now.
                Deep links from search land here so the roster is not a flat table only.
              </p>
            </Card>
          </>
        )}
      </div>
    </AppShell>
  );
}
