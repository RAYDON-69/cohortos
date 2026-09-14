import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTenant } from "../../hooks/useTenant";
import { buildDeskNav } from "../../nav/deskNav";
import { AppShell } from "../../shell/AppShell";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { useLocale } from "../../i18n/LocaleContext";
import { getCentreMode, setCentreMode } from "../../api/client"
import type { ApiError } from "../../api/client"
import "../../components/Button.css";
import "../../components/Card.css";
import "../../shell/AppShell.css";

/**
 * Mode toggle — Portion 18
 * High-stakes, once-per-centre decision with plain-language consequences.
 */

const MODE_COPY: Record<string, { title: string; body: string }> = {
  "offline-first": {
    title: "Offline-first (default)",
    body:
      "The desk keeps a local database and keeps working through power cuts and weak internet. Changes sync when a connection returns. Choose this if attendance, fees, and exams must never wait on the network.",
  },
  "cloud-first": {
    title: "Cloud-first",
    body:
      "The centre of truth is the hosted database. Staff use a local cache only for brief outages. Choose this if the centre has reliable internet and prefers one shared cloud record over a local-first desk.",
  },
  hybrid: {
    title: "Hybrid",
    body:
      "Desk staff stay offline-first on the desktop app; teachers, students, and parents primarily use the cloud-facing web/mobile surfaces. Choose this when the front counter needs offline resilience but mobile users are online.",
  },
};

export function ModeSettingsScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const { tenantId: tid } = useTenant();
  const tenantId = tid || "demo-tenant";

  const [mode, setMode] = useState("offline-first");
  const [runtime, setRuntime] = useState("offline-first");
  const [pending, setPending] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getCentreMode(tenantId);
      setMode(res.mode);
      setRuntime(res.runtime_mode);
    } catch (e) {
      setError((e as ApiError).detail || t("networkError"));
    } finally {
      setLoading(false);
    }
  }, [tenantId, t]);

  useEffect(() => {
    load();
  }, [load]);

  async function onSave() {
    if (!pending) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const res = await setCentreMode(tenantId, pending);
      setMode(res.mode);
      setRuntime(res.runtime_mode);
      setPending(null);
      setSaved(true);
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setSaving(false);
    }
  }

  const nav = buildDeskNav(navigate, "settings");

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb="Owner / Desk · Centre mode">
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
        <Button variant="outline" onClick={() => navigate("/settings/staff")}>Staff</Button>
        <Button variant="outline" onClick={() => navigate("/settings/messaging")}>Messaging</Button>
        <Button variant="outline" onClick={() => navigate("/settings/mode")}>Mode</Button>
        <Button variant="outline" onClick={() => navigate("/attendance")}>← Back to desk</Button>
      </div>
      <h2 className="view-title">Centre mode</h2>
      <p className="caption muted" style={{ marginBottom: 20 }}>
        This is a centre-wide decision, not a casual toggle. Changing it changes where truth lives
        for attendance, fees, and exams.
      </p>

      {error && (
        <div className="warning-banner" role="alert">
          {error}
        </div>
      )}
      {saved && (
        <div
          className="badge badge-neutral-info"
          role="status"
          style={{ marginBottom: 12, display: "inline-flex" }}
        >
          Mode saved · runtime {runtime}
        </div>
      )}

      {loading && <p className="caption muted">{t("loadingView")}</p>}

      <div className="mode-grid">
        {Object.entries(MODE_COPY).map(([key, copy]) => {
          const selected = (pending || mode) === key;
          const current = mode === key;
          return (
            <button
              key={key}
              type="button"
              className={`mode-card ${selected ? "selected" : ""}`}
              onClick={() => setPending(key)}
              aria-pressed={selected}
            >
              <div className="mode-card-title">{copy.title}</div>
              <p className="mode-card-body">{copy.body}</p>
              {current && (
                <span className="badge badge-neutral-info" role="status">
                  Current
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div style={{ marginTop: 20, display: "flex", gap: 12, alignItems: "center" }}>
        <Button
          variant="primary"
          onClick={() => void onSave()}
          loading={saving}
          disabled={!pending || pending === mode}
        >
          Save mode
        </Button>
        {pending && pending !== mode && (
          <span className="caption">Will switch to {pending}</span>
        )}
      </div>

      <style>{`
        .mode-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
          gap: 16px;
        }
        .mode-card {
          text-align: left;
          background: var(--white);
          border: 1px solid var(--border);
          border-radius: 12px;
          padding: 20px;
          cursor: pointer;
          font-family: inherit;
          box-shadow: var(--shadow);
        }
        .mode-card.selected {
          border-color: var(--sage-700);
          background: var(--sage-100);
        }
        .mode-card-title {
          font-weight: 600;
          font-size: 16px;
          margin-bottom: 8px;
          color: var(--ink);
        }
        .mode-card-body {
          font-size: 13px;
          color: var(--slate-700);
          margin: 0 0 12px;
          line-height: 1.5;
        }
      `}</style>
    </AppShell>
  );
}
