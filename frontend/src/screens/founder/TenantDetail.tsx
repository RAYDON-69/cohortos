import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { FormField, TextInput } from "../../components/FormField";
import { ModalConfirm } from "../../components/Confirm";
import { useLocale } from "../../i18n/LocaleContext";
import { founderGetTenant, founderSuspend, founderExtend, founderActivate } from "../../api/client"
import type { FounderTenant, AiMetrics, ApiError } from "../../api/client"
import "../../components/Button.css";
import "../../components/Card.css";
import "../../components/FormField.css";
import "../../components/Confirm.css";
import "../../shell/AppShell.css";

/**
 * Tenant detail / suspend-extend — Portion 23
 * Modal-confirm tier for suspend: states specific business consequence (§4.7).
 */

export function TenantDetailScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const { tenantId = "" } = useParams();
  const [tenant, setTenant] = useState<FounderTenant | null>(null);
  const [metrics, setMetrics] = useState<AiMetrics | null>(null);
  const [reason, setReason] = useState("");
  const [extendDays, setExtendDays] = useState("30");
  const [suspendOpen, setSuspendOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!tenantId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await founderGetTenant(tenantId);
      setTenant(res.tenant);
      setMetrics(res.metrics);
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setLoading(false);
    }
  }, [tenantId, t]);

  useEffect(() => {
    load();
  }, [load]);

  async function onSuspend() {
    if (!tenantId) return;
    setBusy(true);
    try {
      const res = await founderSuspend(tenantId, reason);
      setTenant(res.tenant);
      setSuspendOpen(false);
      setReason("");
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setBusy(false);
    }
  }

  async function onExtend() {
    if (!tenantId) return;
    setBusy(true);
    try {
      const res = await founderExtend(tenantId, Number(extendDays) || 30);
      setTenant(res.tenant);
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setBusy(false);
    }
  }

  async function onActivate() {
    if (!tenantId) return;
    setBusy(true);
    try {
      const res = await founderActivate(tenantId);
      setTenant(res.tenant);
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setBusy(false);
    }
  }

  const nav = [
    { id: "dash", label: "Dashboard", onClick: () => navigate("/founder") },
    { id: "detail", label: "Tenant", active: true },
    { id: "pricing", label: "Pricing", onClick: () => navigate("/founder/pricing") },
  ];

  const name = tenant?.name || "this centre";
  const suspendConsequence = `Suspending ${name} (${tenant?.code || tenantId}) immediately blocks all desk, teacher, and student access for that business until you activate or extend them again. Reason will be audit-logged.`;

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb="Founder · Tenant detail">
      <Button size="sm" variant="ghost" onClick={() => navigate("/founder")}>
        ← Dashboard
      </Button>
      <h2 className="view-title" style={{ marginTop: 8 }}>
        {tenant?.name || "Tenant"}
      </h2>
      {tenant?.code && (
        <p className="caption mono-data" style={{ marginBottom: 16 }}>
          {tenant.code} · {tenant.status}
        </p>
      )}

      {error && (
        <div className="warning-banner" role="alert">
          {error}
        </div>
      )}
      {loading && <p className="caption muted">{t("loadingView")}</p>}

      {tenant && (
        <div className="detail-grid">
          <Card>
            <div className="eyebrow">Centre</div>
            <dl className="detail-dl">
              <div>
                <dt>Status</dt>
                <dd>
                  <span className="badge badge-neutral-info" role="status">
                    {tenant.status}
                  </span>
                </dd>
              </div>
              <div>
                <dt>Tier</dt>
                <dd>{tenant.tier || "—"}</dd>
              </div>
              <div>
                <dt>Students</dt>
                <dd className="mono-data">{tenant.student_count ?? 0}</dd>
              </div>
              <div>
                <dt>Mode</dt>
                <dd>{tenant.mode || "—"}</dd>
              </div>
              {tenant.suspended_reason && (
                <div>
                  <dt>Suspend reason</dt>
                  <dd>{tenant.suspended_reason}</dd>
                </div>
              )}
              {tenant.extended_until && (
                <div>
                  <dt>Extended until</dt>
                  <dd className="mono-data">{tenant.extended_until}</dd>
                </div>
              )}
            </dl>
          </Card>

          <Card variant="insight">
            <div className="eyebrow">AI metrics (no spend)</div>
            <dl className="detail-dl">
              <div>
                <dt>Query volume</dt>
                <dd className="mono-data">{metrics?.query_volume ?? 0}</dd>
              </div>
              <div>
                <dt>429 / rate-limit hits</dt>
                <dd className="mono-data">{metrics?.rate_limit_hits ?? 0}</dd>
              </div>
              <div>
                <dt>Cache hit rate</dt>
                <dd className="mono-data">
                  {((Number(metrics?.cache_hit_rate) || 0) * 100).toFixed(1)}%
                </dd>
              </div>
              <div>
                <dt>MCQ / Written</dt>
                <dd className="mono-data">
                  {metrics?.mcq_count ?? 0} / {metrics?.written_count ?? 0}
                </dd>
              </div>
            </dl>
          </Card>

          <Card variant="featured">
            <div className="eyebrow">Lifecycle actions</div>
            <p className="caption" style={{ marginBottom: 12 }}>
              Suspend is irreversible until activate/extend — use the confirm modal.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
              <Button
                variant="primary"
                className="btn-destructive"
                onClick={() => setSuspendOpen(true)}
                disabled={tenant.status === "suspended"}
              >
                Suspend centre
              </Button>
              <Button
                variant="outline"
                onClick={() => void onActivate()}
                loading={busy}
                disabled={tenant.status === "active"}
              >
                Activate
              </Button>
            </div>
            <FormField id="ext-days" label="Extend by days">
              <TextInput
                id="ext-days"
                type="number"
                value={extendDays}
                onChange={(e) => setExtendDays(e.target.value)}
              />
            </FormField>
            <Button variant="outline" onClick={() => void onExtend()} loading={busy}>
              Extend access
            </Button>
          </Card>
        </div>
      )}

      <ModalConfirm
        open={suspendOpen}
        title={`Suspend ${name}?`}
        consequence={suspendConsequence}
        confirmLabel="Suspend centre"
        cancelLabel="Keep active"
        destructive
        loading={busy}
        onCancel={() => setSuspendOpen(false)}
        onConfirm={() => void onSuspend()}
      />

      {suspendOpen && (
        <div style={{ marginTop: 12 }}>
          <FormField id="sus-reason" label="Reason (audit log)">
            <TextInput
              id="sus-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. non-payment, abuse"
            />
          </FormField>
        </div>
      )}

      <style>{`
        .detail-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
          gap: 16px;
        }
        .detail-dl {
          margin: 8px 0 0;
        }
        .detail-dl > div {
          display: grid;
          grid-template-columns: 140px 1fr;
          gap: 8px;
          padding: 6px 0;
          border-bottom: 1px solid var(--border);
          font-size: 14px;
        }
        .detail-dl dt {
          color: var(--slate-700);
          font-weight: 600;
        }
        .detail-dl dd {
          margin: 0;
        }
      `}</style>
    </AppShell>
  );
}
