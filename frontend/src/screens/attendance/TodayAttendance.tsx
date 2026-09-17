import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { buildDeskNav } from "../../nav/deskNav";
import { AppShell } from "../../shell/AppShell";
import { DataTable } from "../../components/DataTable"
import type { Column } from "../../components/DataTable"
import { AttendanceBadge, SourceBadge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { FormField, SelectInput } from "../../components/FormField";
import { useLocale } from "../../i18n/LocaleContext";
import { getBatchAttendance, listBatches, listAttendanceReviews, markManualAttendance, resolveAttendanceReview, loadTokens } from "../../api/client"
import type { AttendanceRow, BatchRow, ReviewFlag, ApiError } from "../../api/client"
import "../../components/DataTable.css";
import "../../components/Card.css";
import "../../components/FormField.css";
import "../../components/Button.css";
import "../../components/Badge.css";
import "../../shell/AppShell.css";

/**
 * Today's Attendance — Portion 12
 * SPEC §2 [LOCKED]: biometric authoritative; manual fills gaps only.
 * Edge cases made visible: bio vs manual, anti-proxy → review, cross-batch badge,
 * absent = red dot + word, bio/manual conflict = needs review.
 */

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function statusKind(status: string): "present" | "late" | "absent" {
  if (status === "late") return "late";
  if (status === "absent" || status === "review") return "absent";
  return "present";
}

export function TodayAttendanceScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";

  const [batches, setBatches] = useState<BatchRow[]>([]);
  const [batchId, setBatchId] = useState("");
  const [onDate, setOnDate] = useState(todayISO());
  const [rows, setRows] = useState<AttendanceRow[]>([]);
  const [reviews, setReviews] = useState<ReviewFlag[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [marking, setMarking] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const b = await listBatches(tenantId);
      setBatches(b.batches || []);
      const first = batchId || b.batches?.[0]?.id || "";
      if (!batchId && first) setBatchId(first);
      const useBatch = batchId || first;
      if (useBatch) {
        const att = await getBatchAttendance(tenantId, useBatch, onDate);
        setRows(att.rows || []);
      }
      const rev = await listAttendanceReviews(tenantId);
      setReviews(rev.reviews || []);
    } catch (e) {
      const err = e as ApiError;
      setError(err.detail || t("networkError"));
      // Offline: keep previous rows if any — never look broken
    } finally {
      setLoading(false);
    }
  }, [tenantId, batchId, onDate, t]);

  useEffect(() => {
    load();
  }, [load]);

  const openReviewsForDate = useMemo(
    () => reviews.filter((r) => r.date === onDate || !onDate),
    [reviews, onDate]
  );

  const columns: Column<AttendanceRow>[] = [
    {
      key: "roll",
      header: "Roll",
      sortable: true,
      essential: true,
      width: "110px",
      render: (r) => <span className="mono-data">{r.roll || "—"}</span>,
    },
    {
      key: "name",
      header: "Name",
      sortable: true,
      essential: true,
      render: (r) => r.name || "—",
    },
    {
      key: "status",
      header: "Status",
      sortable: true,
      essential: true,
      render: (r) => {
        const st = r.status || "absent";
        const isReview = st === "review" || (r.flags || []).includes("bio_manual_conflict");
        const isCross =
          st === "cross_batch" ||
          r.record?.cross_batch === true ||
          (r.flags || []).includes("cross_batch");
        return (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
            {isReview ? (
              <span className="badge badge-ai-ungrounded" role="status">
                Needs review
              </span>
            ) : (
              <AttendanceBadge
                status={statusKind(st === "cross_batch" ? "present" : st)}
                label={
                  st === "present"
                    ? t("present")
                    : st === "late"
                      ? t("late")
                      : st === "cross_batch"
                        ? t("present")
                        : t("absent")
                }
                showDot
              />
            )}
            {isCross && <SourceBadge status="cross-batch" label={t("crossBatch")} />}
          </div>
        );
      },
    },
    {
      key: "source",
      header: "Source",
      essential: false,
      render: (r) => {
        const src = r.record?.source_precedence || "";
        if (src === "biometric") return <SourceBadge status="biometric" label={t("biometric")} />;
        if (src === "manual") return <SourceBadge status="manual" label={t("manual")} />;
        return <span className="caption muted">—</span>;
      },
    },
    {
      key: "flags",
      header: "Flags",
      essential: false,
      render: (r) => {
        const flags = r.flags || r.record?.flags || [];
        if (!flags.length) return <span className="caption muted">—</span>;
        return (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {flags.map((f) => (
              <span key={f} className="badge badge-ai-confidence-medium" role="status">
                {f === "anti_proxy" ? "Anti-proxy" : f.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        );
      },
    },
    {
      key: "actions",
      header: "",
      essential: true,
      width: "140px",
      render: (r) => (
        <div style={{ display: "flex", gap: 4 }}>
          <Button
            size="sm"
            variant="outline"
            loading={marking === r.student_id + "present"}
            onClick={(e) => {
              e.stopPropagation();
              void mark(r.student_id, "present");
            }}
          >
            Present
          </Button>
          <Button
            size="sm"
            variant="outline"
            loading={marking === r.student_id + "late"}
            onClick={(e) => {
              e.stopPropagation();
              void mark(r.student_id, "late");
            }}
          >
            Late
          </Button>
          <Button
            size="sm"
            variant="ghost"
            loading={marking === r.student_id + "absent"}
            onClick={(e) => {
              e.stopPropagation();
              void mark(r.student_id, "absent");
            }}
          >
            Absent
          </Button>
        </div>
      ),
    },
  ];

  async function mark(studentId: string, status: string) {
    setMarking(studentId + status);
    try {
      await markManualAttendance(tenantId, {
        student_id: studentId,
        on_date: onDate,
        status_or_time: status,
        batch_id: batchId,
      });
      await load();
    } catch (e) {
      const err = e as ApiError;
      setError(err.detail || t("genericError"));
    } finally {
      setMarking(null);
    }
  }

  async function resolve(flag: ReviewFlag, final: string) {
    try {
      await resolveAttendanceReview(tenantId, flag.id, final);
      await load();
    } catch (e) {
      const err = e as ApiError;
      setError(err.detail || t("genericError"));
    }
  }

  const nav = buildDeskNav(navigate, "attendance", {
    attendance: t("navAttendance"),
    admissions: t("navAdmissions"),
    fees: t("navFees") || "Fees",
  });

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb={`Owner / Desk · ${t("navAttendance")}`}>
      <h2 className="view-title">{t("navAttendance")}</h2>
      <p className="caption muted" style={{ marginBottom: 20 }}>
        Biometric is authoritative. Manual fills gaps only. Conflicts go to review.
      </p>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 16, marginBottom: 20, alignItems: "flex-end" }}>
        <FormField id="batch" label="Batch">
          <SelectInput
            id="batch"
            value={batchId}
            onChange={(e) => setBatchId(e.target.value)}
          >
            {batches.length === 0 && <option value="">No batches</option>}
            {batches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.display_name || b.name || b.id}
              </option>
            ))}
          </SelectInput>
        </FormField>
        <FormField id="date" label="Date">
          <input
            id="date"
            type="date"
            className="form-input"
            value={onDate}
            onChange={(e) => setOnDate(e.target.value)}
          />
        </FormField>
        <Button variant="outline" onClick={() => load()} loading={loading}>
          Refresh
        </Button>
      </div>

      {error && (
        <div className="warning-banner" role="alert" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      {openReviewsForDate.length > 0 && (
        <section style={{ marginBottom: 24 }}>
          <div className="eyebrow">Review queue · anti-proxy & bio/manual conflicts</div>
          <div style={{ display: "grid", gap: 12, marginTop: 12 }}>
            {openReviewsForDate.map((flag) => (
              <Card key={flag.id} variant="queue-flagged">
                <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
                  <div>
                    <div className="mono-data">{flag.student_id}</div>
                    <div className="caption">
                      {flag.date} · {String(flag.flag_type || "review")}
                    </div>
                    <p className="caption" style={{ marginTop: 6 }}>
                      Not auto-resolved. Choose final status.
                    </p>
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <Button size="sm" variant="outline" onClick={() => resolve(flag, "present")}>
                      Present
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => resolve(flag, "late")}>
                      Late
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => resolve(flag, "absent")}>
                      Absent
                    </Button>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </section>
      )}

      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(r) => r.student_id}
        loading={loading}
        emptyTitle="No students in this batch for the day"
        emptyBody="Create a batch under Batches, then admit students under Admissions."
      />
    </AppShell>
  );
}
