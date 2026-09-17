import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { buildDeskNav } from "../../nav/deskNav";
import { AppShell } from "../../shell/AppShell";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { FormField, TextInput, SelectInput } from "../../components/FormField";
import { useLocale } from "../../i18n/LocaleContext";
import { listBatches, getBatchDetail, setLateThreshold, addExtraSession, loadTokens, createBatch } from "../../api/client"
import type { BatchRow, ExtraSession, ApiError } from "../../api/client"
import "../../components/Button.css";
import "../../components/Card.css";
import "../../components/FormField.css";
import "../../shell/AppShell.css";

/**
 * Batch settings — Portion 14
 * Late threshold: global default AND per-batch override shown as two distinct values.
 * Extra class: "expiring soon" vs "active"; stops applying after expiry (visible).
 */

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function daysUntil(expiresOn: string): number {
  const a = new Date(todayISO() + "T00:00:00");
  const b = new Date(expiresOn + "T00:00:00");
  return Math.ceil((b.getTime() - a.getTime()) / 86400000);
}

function sessionState(expiresOn: string): "active" | "expiring-soon" | "expired" {
  const d = daysUntil(expiresOn);
  if (d < 0) return "expired";
  if (d <= 7) return "expiring-soon";
  return "active";
}

const DAYS = ["sat", "sun", "mon", "tue", "wed", "thu", "fri"];

export function BatchSettingsScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";

  const [batches, setBatches] = useState<BatchRow[]>([]);
  const [newBatchName, setNewBatchName] = useState("");
  const [newBatchHour, setNewBatchHour] = useState(14);
  const [newBatchDays, setNewBatchDays] = useState<string[]>(["sat", "mon", "wed"]);
  const [creating, setCreating] = useState(false);
  const [createMsg, setCreateMsg] = useState<string | null>(null);
  const [batchId, setBatchId] = useState("");
  const [detail, setDetail] = useState<Awaited<ReturnType<typeof getBatchDetail>> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Late threshold form — two distinct fields
  const [globalLate, setGlobalLate] = useState(12);
  const [batchLate, setBatchLate] = useState(12);
  const [useOverride, setUseOverride] = useState(false);

  // Extra session form
  const [extraDay, setExtraDay] = useState("sat");
  const [extraHour, setExtraHour] = useState(14);
  const [extraExpires, setExtraExpires] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const b = await listBatches(tenantId);
      setBatches(b.batches || []);
      const first = batchId || b.batches?.[0]?.id || "";
      if (!batchId && first) setBatchId(first);
      const useId = batchId || first;
      if (useId) {
        const d = await getBatchDetail(tenantId, useId);
        setDetail(d);
        setGlobalLate(d.late_threshold.global_minutes);
        setBatchLate(d.late_threshold.batch_minutes);
        setUseOverride(d.late_threshold.has_override);
      }
    } catch (e) {
      const err = e as ApiError;
      setError(err.detail || t("networkError"));
    } finally {
      setLoading(false);
    }
  }, [tenantId, batchId, t]);

  useEffect(() => {
    load();
  }, [load]);

  const sessions: ExtraSession[] = useMemo(
    () => (detail?.batch?.extra_sessions as ExtraSession[]) || [],
    [detail]
  );

  async function saveLateThresholds() {
    setSaving(true);
    setError(null);
    try {
      // Always persist global as its own value
      await setLateThreshold(tenantId, globalLate, undefined);
      if (useOverride && batchId) {
        await setLateThreshold(tenantId, batchLate, batchId);
      } else if (batchId) {
        // Clear override by setting batch equal to global via service semantics:
        // service stores per-batch map; setting to global is still an override entry.
        // UI shows has_override from comparison — if user unchecks override, set batch to global.
        await setLateThreshold(tenantId, globalLate, batchId);
      }
      await load();
    } catch (e) {
      const err = e as ApiError;
      setError(err.detail || t("genericError"));
    } finally {
      setSaving(false);
    }
  }

  async function onAddExtra() {
    if (!batchId || !extraExpires) return;
    setSaving(true);
    setError(null);
    try {
      await addExtraSession(tenantId, batchId, {
        day: extraDay,
        hour: extraHour,
        expires_on: extraExpires,
      });
      setExtraExpires("");
      await load();
    } catch (e) {
      const err = e as ApiError;
      setError(err.detail || t("genericError"));
    } finally {
      setSaving(false);
    }
  }

  async function onCreateBatch() {
    if (!newBatchName.trim()) {
      setError("Enter a batch name");
      return;
    }
    if (newBatchDays.length === 0) {
      setError("Select at least one day");
      return;
    }
    setCreating(true);
    setError(null);
    setCreateMsg(null);
    try {
      await createBatch(tenantId, {
        days: newBatchDays,
        hour: newBatchHour,
        name: newBatchName.trim(),
      });
      setCreateMsg(`Created “${newBatchName.trim()}”`);
      setNewBatchName("");
      await load();
      // Notify other screens (Admissions dropdown) to refetch immediately
      try {
        window.dispatchEvent(new CustomEvent("cohortos:batches-changed"));
      } catch {
        /* ignore */
      }
    } catch (e) {
      const err = e as ApiError;
      setError(err.detail || t("genericError"));
    } finally {
      setCreating(false);
    }
  }

  function toggleDay(d: string) {
    setNewBatchDays((prev) =>
      prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]
    );
  }

  const nav = buildDeskNav(navigate, "batches", {
    attendance: t("navAttendance"),
    admissions: t("navAdmissions"),
    fees: t("navFees") || "Fees",
  });

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb="Owner / Desk · Batch settings">
      <h2 className="view-title">Batch settings</h2>
      <p className="caption muted" style={{ marginBottom: 20 }}>
        Create batches here, then admit students and take attendance.
      </p>

      <Card style={{ marginBottom: 24 }}>
        <div className="eyebrow">Create batch</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 12 }}>
          <FormField id="nb-name" label="Batch name">
            <TextInput
              id="nb-name"
              value={newBatchName}
              placeholder="e.g. HSC Physics A"
              onChange={(e) => setNewBatchName(e.target.value)}
            />
          </FormField>
          <FormField id="nb-hour" label="Start hour (0–23)">
            <TextInput
              id="nb-hour"
              type="number"
              min={0}
              max={23}
              value={String(newBatchHour)}
              onChange={(e) => setNewBatchHour(Number(e.target.value))}
            />
          </FormField>
          <div>
            <div className="caption" style={{ marginBottom: 8 }}>Days</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {DAYS.map((d) => (
                <label key={d} style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13 }}>
                  <input
                    type="checkbox"
                    checked={newBatchDays.includes(d)}
                    onChange={() => toggleDay(d)}
                  />
                  {d}
                </label>
              ))}
            </div>
          </div>
          {createMsg && <p className="caption" style={{ color: "var(--sage-700)" }}>{createMsg}</p>}
          <Button variant="primary" onClick={() => void onCreateBatch()} loading={creating}>
            Create batch
          </Button>
        </div>
      </Card>

      {error && (
        <div className="warning-banner" role="alert" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      <FormField id="bs-batch" label="Batch">
        <SelectInput
          id="bs-batch"
          value={batchId}
          onChange={(e) => setBatchId(e.target.value)}
        >
          {batches.map((b) => (
            <option key={b.id} value={b.id}>
              {b.display_name || b.name || b.id}
            </option>
          ))}
        </SelectInput>
      </FormField>

      {loading && <p className="caption muted">{t("loadingView")}</p>}

      {detail && !loading && (
        <>
          <section style={{ marginBottom: 32 }}>
            <div className="eyebrow">Late threshold (minutes after start)</div>
            <Card>
              <div className="threshold-grid">
                <FormField
                  id="global-late"
                  label="Global default"
                  hint="Applies to every batch that does not set an override"
                >
                  <TextInput
                    id="global-late"
                    type="number"
                    min={0}
                    max={120}
                    value={String(globalLate)}
                    onChange={(e) => setGlobalLate(Number(e.target.value))}
                  />
                </FormField>
                <FormField
                  id="batch-late"
                  label="This batch override"
                  hint={
                    useOverride
                      ? `Override active · effective ${batchLate} min`
                      : `Using global · effective ${globalLate} min`
                  }
                >
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
                      <input
                        type="checkbox"
                        checked={useOverride}
                        onChange={(e) => setUseOverride(e.target.checked)}
                      />
                      Use batch-specific override
                    </label>
                    <TextInput
                      id="batch-late"
                      type="number"
                      min={0}
                      max={120}
                      value={String(batchLate)}
                      disabled={!useOverride}
                      onChange={(e) => setBatchLate(Number(e.target.value))}
                    />
                  </div>
                </FormField>
              </div>
              <div className="caption" style={{ marginBottom: 12 }}>
                Effective for this batch:{" "}
                <strong className="mono-data">
                  {useOverride ? batchLate : globalLate} min
                </strong>
                {" · "}
                Global remains <strong className="mono-data">{globalLate} min</strong> for other batches.
              </div>
              <Button variant="primary" onClick={() => void saveLateThresholds()} loading={saving}>
                Save thresholds
              </Button>
            </Card>
          </section>

          <section style={{ marginBottom: 32 }}>
            <div className="eyebrow">Extra class sessions</div>
            <Card>
              <div className="threshold-grid">
                <FormField id="ex-day" label="Day">
                  <SelectInput id="ex-day" value={extraDay} onChange={(e) => setExtraDay(e.target.value)}>
                    {DAYS.map((d) => (
                      <option key={d} value={d}>
                        {d}
                      </option>
                    ))}
                  </SelectInput>
                </FormField>
                <FormField id="ex-hour" label="Hour (24h)">
                  <TextInput
                    id="ex-hour"
                    type="number"
                    min={0}
                    max={23}
                    value={String(extraHour)}
                    onChange={(e) => setExtraHour(Number(e.target.value))}
                  />
                </FormField>
                <FormField id="ex-exp" label="Expires on">
                  <input
                    id="ex-exp"
                    type="date"
                    className="form-input"
                    value={extraExpires}
                    onChange={(e) => setExtraExpires(e.target.value)}
                  />
                </FormField>
              </div>
              <Button
                variant="outline"
                onClick={() => void onAddExtra()}
                loading={saving}
                disabled={!extraExpires}
              >
                Add extra session
              </Button>

              <ul className="session-list">
                {sessions.length === 0 && (
                  <li className="caption muted">No extra sessions for this batch.</li>
                )}
                {sessions.map((s, i) => {
                  const state = sessionState(s.expires_on);
                  return (
                    <li key={`${s.day}-${s.hour}-${s.expires_on}-${i}`} className={`session-item session-${state}`}>
                      <span className="mono-data">
                        {s.day} {String(s.hour).padStart(2, "0")}:00
                      </span>
                      <span className="caption">expires {s.expires_on}</span>
                      {state === "active" && (
                        <span className="badge badge-attendance-present" role="status">
                          Active
                        </span>
                      )}
                      {state === "expiring-soon" && (
                        <span className="badge badge-attendance-late" role="status">
                          Expiring soon
                        </span>
                      )}
                      {state === "expired" && (
                        <span className="badge badge-attendance-absent" role="status">
                          Expired — not applying
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </Card>
          </section>

          <section>
            <div className="eyebrow">Batch detail</div>
            <Card>
              <p>
                <span className="caption">Name · </span>
                {detail.batch.display_name || detail.batch.name || "—"}
              </p>
              <p>
                <span className="caption">Days · </span>
                {((detail.batch.days as string[]) || []).join(", ") || "—"}
              </p>
              <p>
                <span className="caption">Hour · </span>
                <span className="mono-data">{detail.batch.hour ?? "—"}</span>
              </p>
              <p className="caption">
                Irregularity threshold: global {detail.irregularity_threshold.global_days} days
                {detail.irregularity_threshold.has_override
                  ? ` · batch override ${detail.irregularity_threshold.batch_days} days`
                  : " · no batch override"}
              </p>
            </Card>
          </section>
        </>
      )}

      <style>{`
        .threshold-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 16px;
          margin-bottom: 16px;
        }
        .session-list {
          list-style: none;
          margin: 20px 0 0;
          padding: 0;
          border-top: 1px solid var(--border);
          padding-top: 12px;
        }
        .session-item {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 12px;
          padding: 10px 0;
          border-bottom: 1px solid var(--border);
          font-size: 14px;
        }
        .session-item:last-child { border-bottom: none; }
        .session-expired { opacity: 0.75; }
      `}</style>
    </AppShell>
  );
}
