import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { AiBadge } from "../../components/Badge";
import { useLocale } from "../../i18n/LocaleContext";
import { listAiReviewQueue, approveAiItem, rejectAiItem, loadTokens } from "../../api/client"
import type { AiReviewItem, ApiError } from "../../api/client"

/**
 * Teacher AI review queue — Portion 19
 * Grounded vs ungrounded visible; source chunks inline (not behind a click).
 */

export function ReviewQueueScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";

  const [items, setItems] = useState<AiReviewItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [editText, setEditText] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listAiReviewQueue(tenantId);
      setItems(res.items || []);
    } catch (e) {
      setError((e as ApiError).detail || t("networkError"));
    } finally {
      setLoading(false);
    }
  }, [tenantId, t]);

  useEffect(() => {
    load();
  }, [load]);

  async function onApprove(item: AiReviewItem) {
    setBusy(item.id);
    try {
      const edits = editText[item.id]
        ? { answer: editText[item.id] }
        : undefined;
      await approveAiItem(tenantId, item.id, edits);
      await load();
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setBusy(null);
    }
  }

  async function onReject(item: AiReviewItem) {
    setBusy(item.id);
    try {
      await rejectAiItem(tenantId, item.id, "Rejected by teacher");
      await load();
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setBusy(null);
    }
  }

  const nav = [
    { id: "review", label: t("navReview"), active: true },
    { id: "threads", label: t("navThreads"), onClick: () => navigate("/teacher/threads") },
  ];

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb="Teacher · Review queue">
      <h2 className="view-title">Review queue</h2>
      <p className="caption muted" style={{ marginBottom: 20 }}>
        Nothing ungrounded reaches a student without a teacher seeing the source chunks here.
      </p>

      {error && (
        <div className="warning-banner" role="alert">
          {error}
        </div>
      )}
      {loading && <p className="caption muted">{t("loadingView")}</p>}
      {!loading && items.length === 0 && (
        <Card>
          <p>Queue is clear.</p>
        </Card>
      )}

      <div className="queue-list">
        {items.map((item) => {
          const grounded =
            item.grounded === true ||
            (item.content?.source_chunks && item.content.source_chunks.length > 0) ||
            (item.source_chunks && item.source_chunks.length > 0);
          const chunks =
            item.content?.source_chunks || item.source_chunks || [];
          const conf = item.confidence;
          return (
            <Card
              key={item.id}
              variant={grounded ? "queue" : "queue-flagged"}
            >
              <div className="queue-top">
                <div>
                  <div className="eyebrow">
                    {item.subject || "—"} · {item.topic || "item"}
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 6 }}>
                    {grounded ? (
                      <AiBadge status="grounded" label={t("grounded")} />
                    ) : (
                      <AiBadge status="ungrounded" label={t("ungrounded")} />
                    )}
                    {conf != null && conf < 0.65 && (
                      <AiBadge status="confidence-low" label={t("confidenceLow")} />
                    )}
                    {conf != null && conf >= 0.65 && conf < 0.85 && (
                      <AiBadge status="confidence-medium" label={t("confidenceMedium")} />
                    )}
                    {item.review_reason && (
                      <span className="caption">{item.review_reason}</span>
                    )}
                  </div>
                </div>
                {item.impact_score != null && (
                  <span className="mono-data caption">impact {item.impact_score}</span>
                )}
              </div>

              <div className="queue-body">
                {item.content?.question && (
                  <p>
                    <strong>Q.</strong> {String(item.content.question)}
                  </p>
                )}
                {item.content?.answer && (
                  <p>
                    <strong>A.</strong> {String(item.content.answer)}
                  </p>
                )}
              </div>

              {/* Source chunks inline — never hidden behind a click */}
              <div className="source-chunks">
                <div className="eyebrow">Source chunks</div>
                {chunks.length === 0 && (
                  <p className="caption" style={{ color: "var(--error)" }}>
                    No source chunks — treat as ungrounded.
                  </p>
                )}
                {chunks.map((c, i) => (
                  <blockquote key={i} className="chunk">
                    {c.ref && <span className="mono-data caption">{c.ref}</span>}
                    <span>{c.text || JSON.stringify(c)}</span>
                  </blockquote>
                ))}
              </div>

              <textarea
                className="form-input"
                rows={2}
                placeholder="Optional edit before approve"
                value={editText[item.id] || ""}
                onChange={(e) =>
                  setEditText((prev) => ({ ...prev, [item.id]: e.target.value }))
                }
                style={{ marginTop: 12 }}
              />

              <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                <Button
                  size="sm"
                  variant="primary"
                  loading={busy === item.id}
                  onClick={() => void onApprove(item)}
                >
                  Accept
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  loading={busy === item.id}
                  onClick={() => void onReject(item)}
                >
                  Reject
                </Button>
              </div>
            </Card>
          );
        })}
      </div>

      <style>{`
        .queue-list { display: grid; gap: 16px; }
        .queue-top {
          display: flex;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 10px;
        }
        .queue-body { font-size: 14px; margin-bottom: 12px; }
        .source-chunks {
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
          color: var(--ink);
        }
      `}</style>
    </AppShell>
  );
}
