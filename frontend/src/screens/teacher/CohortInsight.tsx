import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { FormField, TextInput, SelectInput } from "../../components/FormField";
import { useLocale } from "../../i18n/LocaleContext";
import { listBatches, getTopicHeatmap, getStruggleList, generateRecapDraft, loadTokens } from "../../api/client"
import type { BatchRow, HeatmapTopic, StruggleRow, ApiError } from "../../api/client"
import "../../components/FormField.css";
import "../../shell/AppShell.css";

/**
 * Cohort insight → recap draft — Portion 20
 * "Generate recap draft" closes the loop into the Portion 19 review queue.
 */

export function CohortInsightScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";

  const [batches, setBatches] = useState<BatchRow[]>([]);
  const [batchId, setBatchId] = useState("");
  const [topics, setTopics] = useState<HeatmapTopic[]>([]);
  const [struggle, setStruggle] = useState<StruggleRow[]>([]);
  const [subject, setSubject] = useState("Physics");
  const [topic, setTopic] = useState("");
  const [loading, setLoading] = useState(true);
  const [drafting, setDrafting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [queued, setQueued] = useState<string | null>(null);

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
        const [hm, st] = await Promise.all([
          getTopicHeatmap(tenantId, useBatch),
          getStruggleList(tenantId, useBatch),
        ]);
        setTopics(hm.topics || []);
        setStruggle(st.students || []);
        if (!topic && hm.topics?.[0]) setTopic(hm.topics[0].chapter_or_topic);
      }
    } catch (e) {
      setError((e as ApiError).detail || t("networkError"));
    } finally {
      setLoading(false);
    }
  }, [tenantId, batchId, topic, t]);

  useEffect(() => {
    load();
  }, [load]);

  async function onGenerateRecap() {
    if (!topic.trim()) return;
    setDrafting(true);
    setError(null);
    setQueued(null);
    try {
      const severity =
        topics.find((x) => x.chapter_or_topic === topic)?.mean_percentage != null
          ? Math.max(
              0.1,
              1 - (topics.find((x) => x.chapter_or_topic === topic)!.mean_percentage || 0) / 100
            )
          : 0.8;
      const res = await generateRecapDraft(tenantId, {
        subject,
        topic: topic.trim(),
        cohort_size: Math.max(1, struggle.length || 3),
        weakness_severity: severity,
      });
      setQueued(res.item?.id || "queued");
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setDrafting(false);
    }
  }

  const maxMean = Math.max(1, ...topics.map((x) => x.mean_percentage));

  const nav = [
    { id: "review", label: t("navReview"), onClick: () => navigate("/teacher/review") },
    { id: "style", label: "Style profile", onClick: () => navigate("/teacher/style") },
    { id: "bank", label: "Item bank", onClick: () => navigate("/teacher/item-bank") },
    { id: "insight", label: "Cohort insight", active: true },
    { id: "ocr", label: "OCR (beta)", onClick: () => navigate("/teacher/ocr") },
  ];

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb="Teacher · Cohort insight">
      <h2 className="view-title">Cohort insight</h2>
      <p className="caption muted" style={{ marginBottom: 20 }}>
        Aggregate weakness and struggle signals. Generating a recap draft sends it into the same
        review queue teachers already use — nothing student-facing without approval.
      </p>

      <FormField id="ci-batch" label="Batch">
        <SelectInput id="ci-batch" value={batchId} onChange={(e) => setBatchId(e.target.value)}>
          {batches.map((b) => (
            <option key={b.id} value={b.id}>
              {b.display_name || b.name || b.id}
            </option>
          ))}
        </SelectInput>
      </FormField>

      {error && (
        <div className="warning-banner" role="alert">
          {error}
        </div>
      )}
      {loading && <p className="caption muted">{t("loadingView")}</p>}

      <div className="insight-grid">
        <Card variant="insight">
          <div className="eyebrow">Topic weakness heatmap</div>
          {topics.length === 0 && !loading && (
            <p className="caption muted">No topic results yet.</p>
          )}
          <ul className="heatmap">
            {topics.map((tp) => (
              <li key={tp.chapter_or_topic}>
                <button
                  type="button"
                  className="heatmap-pick"
                  onClick={() => setTopic(tp.chapter_or_topic)}
                >
                  <span>{tp.chapter_or_topic}</span>
                  <span className="mono-data">{tp.mean_percentage}%</span>
                </button>
                <div className="heatmap-bar-track" aria-hidden="true">
                  <div
                    className="heatmap-bar"
                    style={{
                      width: `${Math.min(100, (tp.mean_percentage / maxMean) * 100)}%`,
                      background:
                        tp.mean_percentage < 40
                          ? "var(--error)"
                          : tp.mean_percentage < 60
                            ? "var(--gold-500)"
                            : "var(--sage-700)",
                    }}
                  />
                </div>
              </li>
            ))}
          </ul>
        </Card>

        <Card variant="insight">
          <div className="eyebrow">Students likely to struggle</div>
          {struggle.length === 0 && !loading && (
            <p className="caption muted">No students flagged.</p>
          )}
          <ul className="struggle-list">
            {struggle.map((s) => (
              <li key={s.student_id}>
                <span className="mono-data">{s.roll}</span>
                <span>{s.name}</span>
                <span className="caption">
                  avg {s.recent_avg_percentage ?? "—"}% · {(s.reason || "").replace(/_/g, " ")}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card variant="featured" style={{ marginTop: 24 } as React.CSSProperties}>
        <div className="eyebrow">Generate recap draft → review queue</div>
        <p className="caption" style={{ marginBottom: 12 }}>
          This action calls the teach analytics path and lands a{" "}
          <strong>needs_review</strong> item in the Portion 19 queue. It does not publish to
          students.
        </p>
        <FormField id="ci-subject" label="Subject">
          <TextInput id="ci-subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
        </FormField>
        <FormField id="ci-topic" label="Topic" required>
          <TextInput id="ci-topic" value={topic} onChange={(e) => setTopic(e.target.value)} />
        </FormField>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          <Button
            variant="primary"
            onClick={() => void onGenerateRecap()}
            loading={drafting}
            disabled={!topic.trim()}
          >
            Generate recap draft
          </Button>
          {queued && (
            <>
              <span className="badge badge-neutral-info" role="status">
                Queued for review · {queued}
              </span>
              <Button size="sm" variant="outline" onClick={() => navigate("/teacher/review")}>
                Open review queue
              </Button>
            </>
          )}
        </div>
      </Card>

      <style>{`
        .insight-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
          gap: 20px;
        }
        .heatmap, .struggle-list {
          list-style: none;
          margin: 12px 0 0;
          padding: 0;
        }
        .heatmap li { margin-bottom: 12px; }
        .heatmap-pick {
          display: flex;
          justify-content: space-between;
          width: 100%;
          background: none;
          border: none;
          padding: 0;
          font: inherit;
          cursor: pointer;
          color: var(--ink);
        }
        .heatmap-bar-track {
          height: 10px;
          background: var(--sage-100);
          border-radius: 100px;
          overflow: hidden;
          margin-top: 4px;
        }
        .heatmap-bar {
          height: 100%;
          border-radius: 100px;
        }
        .struggle-list li {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          padding: 8px 0;
          border-bottom: 1px solid var(--border);
          font-size: 14px;
        }
      `}</style>
    </AppShell>
  );
}
