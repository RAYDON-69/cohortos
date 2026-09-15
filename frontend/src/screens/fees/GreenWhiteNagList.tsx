import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { buildDeskNav } from "../../nav/deskNav";
import { AppShell } from "../../shell/AppShell";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { Badge, PaymentBadge } from "../../components/Badge";
import { FormField, SelectInput, TextInput } from "../../components/FormField";
import { useLocale } from "../../i18n/LocaleContext";
import { listBatches, getDelayedCandidates, setNotifyFlag, loadTokens } from "../../api/client"
import type { PaymentRow, BatchRow, ApiError } from "../../api/client"
import "../../components/Button.css";
import "../../components/Card.css";
import "../../components/Badge.css";
import "../../components/FormField.css";
import "../../shell/AppShell.css";

/**
 * Green/white nag list — Portion 15
 * White stays white (persistent label, not a color swap that looks temporary).
 * Irregular-excluded shown with explanation + link to shared threshold concept.
 */

function currentYearMonth() {
  const d = new Date();
  return { year: d.getFullYear(), month: d.getMonth() + 1 };
}

export function GreenWhiteNagListScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";
  const ym = currentYearMonth();

  const [batches, setBatches] = useState<BatchRow[]>([]);
  const [batchId, setBatchId] = useState("");
  const [year, setYear] = useState(ym.year);
  const [month, setMonth] = useState(ym.month);
  const [green, setGreen] = useState<PaymentRow[]>([]);
  const [white, setWhite] = useState<PaymentRow[]>([]);
  const [irregular, setIrregular] = useState<PaymentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

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
        const res = await getDelayedCandidates(tenantId, useBatch, year, month);
        setGreen(res.will_notify || []);
        setWhite(res.suppressed_white || []);
        setIrregular(res.excluded_irregular || []);
      }
    } catch (e) {
      const err = e as ApiError;
      setError(err.detail || t("networkError"));
    } finally {
      setLoading(false);
    }
  }, [tenantId, batchId, year, month, t]);

  useEffect(() => {
    load();
  }, [load]);

  async function toggle(studentId: string, next: "green" | "white") {
    setBusy(studentId);
    try {
      await setNotifyFlag(tenantId, {
        student_id: studentId,
        year,
        month,
        flag: next,
      });
      await load();
    } catch (e) {
      const err = e as ApiError;
      setError(err.detail || t("genericError"));
    } finally {
      setBusy(null);
    }
  }

  const nav = buildDeskNav(navigate, "fees", { attendance: t("navAttendance"), admissions: t("navAdmissions"), fees: t("navFees") || "Fees" });

  function RowList({
    title,
    rows,
    empty,
    kind,
  }: {
    title: string;
    rows: PaymentRow[];
    empty: string;
    kind: "green" | "white" | "irregular";
  }) {
    return (
      <section style={{ marginBottom: 28 }}>
        <div className="eyebrow">{title}</div>
        <Card>
          {rows.length === 0 && <p className="caption muted">{empty}</p>}
          <ul className="nag-list">
            {rows.map((r) => (
              <li key={r.student_id}>
                <span className="mono-data">{r.roll}</span>
                <span>{r.name}</span>
                {kind === "green" && (
                  <>
                    <Badge kind={{ vocab: "neutral", status: "info" }} label="Green · will receive reminder" showDot />
                    <Button
                      size="sm"
                      variant="outline"
                      loading={busy === r.student_id}
                      onClick={() => void toggle(r.student_id, "white")}
                    >
                      Set white
                    </Button>
                  </>
                )}
                {kind === "white" && (
                  <>
                    <Badge kind={{ vocab: "neutral", status: "neutral" }} label="White · stays white (no auto-reset)" showDot />
                    <Button
                      size="sm"
                      variant="outline"
                      loading={busy === r.student_id}
                      onClick={() => void toggle(r.student_id, "green")}
                    >
                      Set green
                    </Button>
                  </>
                )}
                {kind === "irregular" && (
                  <Badge kind={{ vocab: "attendance", status: "late" }} label="Excluded · irregular attendance" showDot />
                )}
              </li>
            ))}
          </ul>
        </Card>
      </section>
    );
  }

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb="Owner / Desk · Green / white nag list">
      <h2 className="view-title">Green / white nag list</h2>
      <p className="caption muted" style={{ marginBottom: 20 }}>
        White stays white until a clerk changes it. Irregular students are excluded by the shared
        attendance threshold — one rule for attendance and fees.
      </p>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 16, marginBottom: 20, alignItems: "flex-end" }}>
        <FormField id="nag-batch" label="Batch">
          <SelectInput id="nag-batch" value={batchId} onChange={(e) => setBatchId(e.target.value)}>
            {batches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.display_name || b.name || b.id}
              </option>
            ))}
          </SelectInput>
        </FormField>
        <FormField id="nag-year" label="Year">
          <TextInput
            id="nag-year"
            type="number"
            value={String(year)}
            onChange={(e) => setYear(Number(e.target.value))}
          />
        </FormField>
        <FormField id="nag-month" label="Month">
          <SelectInput
            id="nag-month"
            value={String(month)}
            onChange={(e) => setMonth(Number(e.target.value))}
          >
            {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </SelectInput>
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

      {loading && <p className="caption muted">{t("loadingView")}</p>}

      {!loading && (
        <>
          <RowList
            title={`Will notify (green) · ${green.length}`}
            rows={green}
            empty="No unpaid green students this cycle."
            kind="green"
          />
          <RowList
            title={`Suppressed (white) · ${white.length}`}
            rows={white}
            empty="No white-flagged unpaid students."
            kind="white"
          />
          <RowList
            title={`Excluded by irregularity threshold · ${irregular.length}`}
            rows={irregular}
            empty="No irregular exclusions this cycle."
            kind="irregular"
          />
          {irregular.length > 0 && (
            <Card variant="insight">
              <div className="eyebrow">Shared threshold</div>
              <p style={{ margin: 0, fontSize: 14 }}>
                These students fall below the attendance irregularity threshold (same setting used
                for absence messages). They are excluded from fee reminders on purpose — one
                consolidated rule, not a separate fee-only filter. Adjust the threshold under Batch
                settings if needed.
              </p>
              <div style={{ marginTop: 12 }}>
                <Button size="sm" variant="outline" onClick={() => navigate("/batches")}>
                  Open batch settings
                </Button>
              </div>
            </Card>
          )}
        </>
      )}

      <style>{`
        .nag-list {
          list-style: none;
          margin: 0;
          padding: 0;
        }
        .nag-list li {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 12px;
          padding: 10px 0;
          border-bottom: 1px solid var(--border);
          font-size: 14px;
        }
        .nag-list li:last-child { border-bottom: none; }
      `}</style>
    </AppShell>
  );
}
