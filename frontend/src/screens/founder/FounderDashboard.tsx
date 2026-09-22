import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { DataTable } from "../../components/DataTable"
import type { Column } from "../../components/DataTable"
import { useLocale } from "../../i18n/LocaleContext";
import { founderDashboard } from "../../api/client"
import type { FounderTenantSummary, ApiError } from "../../api/client"

/**
 * Founder dashboard — Portion 23
 * AI-usage metrics only: query volume, 429 rate, cache hit rate, MCQ vs written.
 * Never shows spend / billing [SPEC §10 LOCKED].
 */

export function FounderDashboardScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const [counts, setCounts] = useState({
    tenant_count: 0,
    active: 0,
    suspended: 0,
    trial: 0,
  });
  const [rows, setRows] = useState<FounderTenantSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await founderDashboard();
      setCounts({
        tenant_count: res.tenant_count,
        active: res.active,
        suspended: res.suspended,
        trial: res.trial,
      });
      setRows(res.tenants || []);
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  const columns: Column<FounderTenantSummary>[] = [
    {
      key: "name",
      header: "Centre",
      essential: true,
      sortable: true,
      render: (r) => (
        <button
          type="button"
          className="linkish"
          onClick={() => navigate(`/founder/tenants/${r.tenant_id}`)}
        >
          <strong>{r.name || "—"}</strong>
          <span className="caption mono-data" style={{ display: "block" }}>
            {r.code}
          </span>
        </button>
      ),
    },
    {
      key: "status",
      header: "Status",
      essential: true,
      render: (r) => (
        <span className={`badge badge-neutral-info`} role="status">
          {r.status || "—"}
        </span>
      ),
    },
    {
      key: "tier",
      header: "Tier",
      essential: false,
      render: (r) => r.tier || "—",
    },
    {
      key: "qv",
      header: "Queries",
      essential: true,
      render: (r) => (
        <span className="mono-data">{r.metrics?.query_volume ?? 0}</span>
      ),
    },
    {
      key: "rl",
      header: "429 hits",
      essential: true,
      render: (r) => (
        <span className="mono-data">{r.metrics?.rate_limit_hits ?? 0}</span>
      ),
    },
    {
      key: "cache",
      header: "Cache hit",
      essential: true,
      render: (r) => {
        const rate = Number(r.metrics?.cache_hit_rate ?? 0);
        return <span className="mono-data">{(rate * 100).toFixed(1)}%</span>;
      },
    },
    {
      key: "split",
      header: "MCQ / Written",
      essential: true,
      render: (r) => (
        <span className="mono-data">
          {r.metrics?.mcq_count ?? 0} / {r.metrics?.written_count ?? 0}
        </span>
      ),
    },
  ];

  const nav = [
    { id: "dash", label: "Dashboard", active: true },
    { id: "provision", label: "Provision", onClick: () => navigate("/founder/provision") },
    { id: "pricing", label: "Pricing", onClick: () => navigate("/founder/pricing") },
  ];

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb="Founder · Dashboard">
      <h2 className="view-title">Tenant dashboard</h2>
      <p className="caption muted" style={{ marginBottom: 16 }}>
        AI usage only — query volume, rate-limit hits, cache hit rate, MCQ vs written. Billing
        spend is intentionally not shown.
      </p>

      {error && (
        <div className="warning-banner" role="alert">
          {error}
        </div>
      )}

      <div className="founder-kpis">
        <Card>
          <div className="eyebrow">Tenants</div>
          <div className="kpi-value mono-data">{counts.tenant_count}</div>
        </Card>
        <Card>
          <div className="eyebrow">Active</div>
          <div className="kpi-value mono-data">{counts.active}</div>
        </Card>
        <Card>
          <div className="eyebrow">Trial</div>
          <div className="kpi-value mono-data">{counts.trial}</div>
        </Card>
        <Card>
          <div className="eyebrow">Suspended</div>
          <div className="kpi-value mono-data">{counts.suspended}</div>
        </Card>
      </div>

      <div style={{ margin: "16px 0", display: "flex", gap: 8 }}>
        <Button size="sm" variant="outline" onClick={() => void load()}>
          Refresh
        </Button>
        <Button size="sm" variant="primary" onClick={() => navigate("/founder/provision")}>
          Provision centre
        </Button>
      </div>

      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(r) => r.tenant_id}
        loading={loading}
        emptyTitle="No tenants yet"
        emptyBody="Provision the first centre to see AI-usage metrics here."
        defaultPageSize={25}
      />

      <style>{`
        .founder-kpis {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
          gap: 12px;
          margin-bottom: 8px;
        }
        .kpi-value {
          font-size: 28px;
          font-weight: 700;
          color: var(--ink);
        }
        .linkish {
          background: none;
          border: none;
          padding: 0;
          font: inherit;
          text-align: left;
          cursor: pointer;
          color: var(--ink);
        }
        .linkish:hover strong {
          text-decoration: underline;
        }
      `}</style>
    </AppShell>
  );
}
