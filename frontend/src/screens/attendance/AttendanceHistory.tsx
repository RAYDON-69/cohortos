import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { buildDeskNav } from "../../nav/deskNav";
import { AppShell } from "../../shell/AppShell";
import { AttendanceBadge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { FormField, SelectInput } from "../../components/FormField";
import { useLocale } from "../../i18n/LocaleContext";
import { getAbsentees, listBatches, loadTokens } from "../../api/client"
import type { AbsenteeDay, BatchRow, ApiError } from "../../api/client"

/**
 * Attendance history multi-day — Portion 12
 * SPEC §2: prior day's absentees, expandable to more days back (teacher rebuke view).
 */

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

export function AttendanceHistoryScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";

  const [batches, setBatches] = useState<BatchRow[]>([]);
  const [batchId, setBatchId] = useState("");
  const [onDate, setOnDate] = useState(todayISO());
  const [daysBack, setDaysBack] = useState(1);
  const [days, setDays] = useState<AbsenteeDay[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

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
        const res = await getAbsentees(tenantId, useBatch, onDate, daysBack);
        setDays(res.days || []);
      }
    } catch (e) {
      const err = e as ApiError;
      setError(err.detail || t("networkError"));
    } finally {
      setLoading(false);
    }
  }, [tenantId, batchId, onDate, daysBack, t]);

  useEffect(() => {
    load();
  }, [load]);

  const nav = buildDeskNav(navigate, "history", { attendance: t("navAttendance"), admissions: t("navAdmissions"), fees: t("navFees") || "Fees" });

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb={`Owner / Desk · Absentees`}>
      <div data-testid="attendance-history"><h2 className="view-title">Absentee history</h2>
      <p className="caption muted" style={{ marginBottom: 20 }}>
        Prior day&apos;s absentees — expand further back for the rebuke workflow.
      </p>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 16, marginBottom: 20, alignItems: "flex-end" }}>
        <FormField id="h-batch" label="Batch">
          <SelectInput id="h-batch" value={batchId} onChange={(e) => setBatchId(e.target.value)}>
            {batches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.display_name || b.name || b.id}
              </option>
            ))}
          </SelectInput>
        </FormField>
        <FormField id="h-date" label="From date">
          <input
            id="h-date"
            type="date"
            className="form-input"
            value={onDate}
            onChange={(e) => setOnDate(e.target.value)}
          />
        </FormField>
        <FormField id="h-days" label="Days back">
          <SelectInput
            id="h-days"
            value={String(daysBack)}
            onChange={(e) => setDaysBack(Number(e.target.value))}
          >
            {[1, 3, 7, 14].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </SelectInput>
        </FormField>
        <Button variant="outline" onClick={() => load()} loading={loading}>
          Load
        </Button>
      </div>

      {error && (
        <div className="warning-banner" role="alert">
          {error}
        </div>
      )}

      {loading && (
        <div className="caption muted" style={{ padding: 24 }}>
          {t("loadingView")}
        </div>
      )}

      {!loading && days.length === 0 && (
        <Card>
          <p>No absentee data for this range.</p>
        </Card>
      )}

      <div style={{ display: "grid", gap: 16 }}>
        {days.map((day) => {
          const isOpen = expanded[day.date] ?? day.count > 0;
          return (
            <Card key={day.date} variant="standard">
              <button
                type="button"
                className="history-day-toggle"
                onClick={() => setExpanded((s) => ({ ...s, [day.date]: !isOpen }))}
                aria-expanded={isOpen}
              >
                <span className="mono-data">{day.date}</span>
                <span>
                  <AttendanceBadge status="absent" label={`${day.count} ${t("absent")}`} showDot />
                </span>
                <span className="caption">{isOpen ? "Hide" : "Show"}</span>
              </button>
              {isOpen && (
                <ul className="absentee-list">
                  {day.absentees.length === 0 && (
                    <li className="caption muted">No absentees this day.</li>
                  )}
                  {day.absentees.map((a) => (
                    <li key={a.student_id}>
                      <span className="mono-data">{a.roll}</span>
                      <span>{a.name}</span>
                      <AttendanceBadge status="absent" label={t("absent")} showDot />
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          );
        })}
      </div>

      <style>{`
        .history-day-toggle {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          width: 100%;
          background: none;
          border: none;
          padding: 0;
          cursor: pointer;
          font-family: inherit;
          text-align: left;
        }
        .absentee-list {
          list-style: none;
          margin: 16px 0 0;
          padding: 0;
          border-top: 1px solid var(--border);
          padding-top: 12px;
        }
        .absentee-list li {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 8px 0;
          border-bottom: 1px solid var(--border);
          font-size: 14px;
        }
        .absentee-list li:last-child { border-bottom: none; }
      `}</style>
    </div></AppShell>
  );
}
