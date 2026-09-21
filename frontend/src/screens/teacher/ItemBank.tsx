import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { DataTable } from "../../components/DataTable"
import type { Column } from "../../components/DataTable"
import { FormField, TextInput } from "../../components/FormField";
import { useLocale } from "../../i18n/LocaleContext";
import { listItemBank, getItemHistory, pushItemToBank, loadTokens } from "../../api/client"
import type { ItemBankRow, ItemHistoryEntry, ApiError } from "../../api/client"
import "../../components/DataTable.css";
import "../../components/FormField.css";
import "../../shell/AppShell.css";

/**
 * Exam item bank — Portion 20
 * Provenance tag: AI-originated (teacher-approved) vs teacher-authored.
 * Version/audit history: reverse-chronological log.
 */

export function ItemBankScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";

  const [items, setItems] = useState<ItemBankRow[]>([]);
  const [subject, setSubject] = useState("");
  const [selected, setSelected] = useState<ItemBankRow | null>(null);
  const [history, setHistory] = useState<ItemHistoryEntry[]>([]);
  const [chunks, setChunks] = useState<{ text?: string; ref?: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listItemBank(tenantId, subject || undefined);
      setItems(res.items || []);
    } catch (e) {
      setError((e as ApiError).detail || t("networkError"));
    } finally {
      setLoading(false);
    }
  }, [tenantId, subject, t]);

  useEffect(() => {
    load();
  }, [load]);

  async function openHistory(item: ItemBankRow) {
    setSelected(item);
    try {
      const res = await getItemHistory(tenantId, item.id);
      setHistory(res.history || []);
      setChunks(res.source_chunks || []);
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    }
  }

  async function onPush(item: ItemBankRow) {
    setBusy(true);
    try {
      await pushItemToBank(tenantId, item.id);
      await load();
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<ItemBankRow>[] = [
    {
      key: "topic",
      header: "Topic",
      essential: true,
      render: (r) => (
        <span>
          {r.topic || "—"}
          <span className="caption" style={{ display: "block" }}>
            {r.subject}
          </span>
        </span>
      ),
    },
    {
      key: "provenance",
      header: "Provenance",
      essential: true,
      render: (r) => {
        const ai = r.provenance === "ai_approved";
        return (
          <span
            className={ai ? "badge badge-ai-grounded" : "badge badge-neutral-info"}
            role="status"
          >
            {ai ? "AI · teacher-approved" : "Teacher-authored"}
          </span>
        );
      },
    },
    {
      key: "bank",
      header: "Exam bank",
      essential: false,
      render: (r) =>
        r.in_exam_bank ? (
          <span className="badge badge-neutral-info" role="status">
            In bank
          </span>
        ) : (
          <span className="caption muted">Not pushed</span>
        ),
    },
    {
      key: "actions",
      header: "Actions",
      essential: true,
      render: (r) => (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <Button size="sm" variant="outline" onClick={() => void openHistory(r)}>
            History
          </Button>
          {!r.in_exam_bank && (
            <Button size="sm" variant="ghost" loading={busy} onClick={() => void onPush(r)}>
              Push to bank
            </Button>
          )}
        </div>
      ),
    },
  ];

  const nav = [
    { id: "review", label: t("navReview"), onClick: () => navigate("/teacher/review") },
    { id: "style", label: "Style profile", onClick: () => navigate("/teacher/style") },
    { id: "bank", label: "Item bank", active: true },
    { id: "insight", label: "Cohort insight", onClick: () => navigate("/teacher/insight") },
    { id: "ocr", label: "OCR (beta)", onClick: () => navigate("/teacher/ocr") },
  ];

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb="Teacher · Exam item bank">
      <h2 className="view-title">Exam item bank</h2>
      <p className="caption muted" style={{ marginBottom: 16 }}>
        Approved items only. Provenance tags keep AI-approved vs teacher-authored legible for
        audit.
      </p>

      <FormField id="ib-subject" label="Filter subject">
        <TextInput
          id="ib-subject"
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          placeholder="e.g. Physics"
        />
      </FormField>
      <Button size="sm" variant="outline" onClick={() => void load()} style={{ marginBottom: 16 }}>
        Refresh
      </Button>

      {error && (
        <div className="warning-banner" role="alert">
          {error}
        </div>
      )}

      <DataTable
        columns={columns}
        rows={items}
        rowKey={(r) => r.id}
        loading={loading}
        emptyTitle="No approved items yet"
        emptyBody="Approve items in the review queue, then they appear here."
      />

      {selected && (
        <Card variant="insight" style={{ marginTop: 24 } as React.CSSProperties}>
          <div className="eyebrow">Version / audit history · {selected.topic || selected.id}</div>
          <p className="caption">
            Status {selected.status} · version {(selected as ItemBankRow).version ?? "—"}
          </p>
          <ol className="history-log">
            {history.length === 0 && (
              <li className="caption muted">No history entries yet.</li>
            )}
            {history.map((h, i) => (
              <li key={i}>
                <span className="mono-data">{h.at || "—"}</span>
                <strong>{h.action || "—"}</strong>
                <span className="caption">by {h.by || "—"}</span>
                {h.status && (
                  <span className="badge badge-neutral-info" role="status">
                    {h.status}
                  </span>
                )}
                {h.reason && <span className="caption">· {h.reason}</span>}
              </li>
            ))}
          </ol>
          {chunks.length > 0 && (
            <div className="source-chunks">
              <div className="eyebrow">Source chunks</div>
              {chunks.map((c, i) => (
                <blockquote key={i} className="chunk">
                  {c.ref && <span className="mono-data caption">{c.ref} </span>}
                  {c.text || JSON.stringify(c)}
                </blockquote>
              ))}
            </div>
          )}
          <Button size="sm" variant="ghost" onClick={() => setSelected(null)} style={{ marginTop: 12 }}>
            Close history
          </Button>
        </Card>
      )}

      <style>{`
        .history-log {
          list-style: none;
          margin: 12px 0 0;
          padding: 0;
        }
        .history-log li {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          align-items: center;
          padding: 8px 0;
          border-bottom: 1px solid var(--border);
          font-size: 13px;
        }
        .source-chunks {
          margin-top: 16px;
          background: var(--cream-bg);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 12px;
        }
        .chunk {
          margin: 8px 0 0;
          padding: 8px 12px;
          border-left: 3px solid var(--sage-300);
          font-size: 13px;
        }
        .badge-ai-grounded {
          background: var(--sage-100);
          color: var(--sage-900);
          border-radius: 100px;
          padding: 3px 10px;
          font-size: 11px;
          font-weight: 600;
        }
      `}</style>
    </AppShell>
  );
}
