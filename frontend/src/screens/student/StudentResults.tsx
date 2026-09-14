import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { MobileShell } from "../../shell/MobileShell";
import { LanguageToggle } from "../../components/LanguageToggle";
import { DataTable } from "../../components/DataTable"
import type { Column } from "../../components/DataTable"
import { useLocale } from "../../i18n/LocaleContext";
import { getStudentResultsHistory, loadTokens } from "../../api/client"
import type { ExamResultRow, ApiError } from "../../api/client"
import { loadStudentSession } from "./studentContext";
import "../../components/DataTable.css";
import "../../components/LanguageToggle.css";
import "../../shell/MobileShell.css";

/**
 * Results history — Portion 21
 * Read-only, permanent. No edit/delete affordance.
 */

export function StudentResultsScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";
  const session = loadStudentSession();

  const [rows, setRows] = useState<ExamResultRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!session.studentId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await getStudentResultsHistory(tenantId, session.studentId);
      setRows(res.results || []);
    } catch (e) {
      setError((e as ApiError).detail || t("networkError"));
    } finally {
      setLoading(false);
    }
  }, [tenantId, session.studentId, t]);

  useEffect(() => {
    load();
  }, [load]);

  const columns: Column<ExamResultRow>[] = [
    {
      key: "date",
      header: "Date",
      essential: true,
      render: (r) => <span className="mono-data">{r.exam_date || "—"}</span>,
    },
    {
      key: "topic",
      header: "Topic",
      essential: true,
      render: (r) => r.chapter_or_topic || "—",
    },
    {
      key: "pct",
      header: "%",
      essential: true,
      render: (r) =>
        r.is_absent ? (
          <span className="badge badge-attendance-absent" role="status">
            Absent
          </span>
        ) : (
          <span className="mono-data">{r.percentage ?? "—"}</span>
        ),
    },
  ];

  const tabs = [
    { id: "home", label: t("navHome"), onClick: () => navigate("/student") },
    { id: "solve", label: t("navSolve"), onClick: () => navigate("/student/solve") },
    { id: "vault", label: t("navVault"), onClick: () => navigate("/student/vault") },
    { id: "results", label: t("navResults"), active: true },
  ];

  return (
    <MobileShell centreName={t("appName")} tabs={tabs} languageSlot={<LanguageToggle />}>
      <h1 className="view-title" style={{ fontSize: 22 }}>
        {t("navResults")}
      </h1>
      <p className="caption muted" style={{ marginBottom: 16 }}>
        Permanent history — read-only. Results are never deleted.
      </p>

      {!session.studentId && (
        <div className="warning-banner" role="status">
          Link your admission on Home to see results.
        </div>
      )}
      {error && (
        <div className="warning-banner" role="alert">
          {error}
        </div>
      )}

      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(r) => String(r.id || `${r.exam_id}-${r.exam_date}`)}
        loading={loading}
        emptyTitle="No results yet"
        emptyBody="After exams are entered, they appear here permanently."
      />
    </MobileShell>
  );
}
