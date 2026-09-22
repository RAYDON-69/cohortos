import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { buildDeskNav } from "../../nav/deskNav";
import { AppShell } from "../../shell/AppShell";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { FormField, SelectInput } from "../../components/FormField";
import { useLocale } from "../../i18n/LocaleContext";
import { listBatches, getTopicHeatmap, getStruggleList, listExams, getExamSummary, loadTokens } from "../../api/client"
import type { BatchRow, HeatmapTopic, StruggleRow, ExamRow, ExamSummary, ApiError } from "../../api/client"

/**
 * Exam / batch analytics — Portion 16
 * Layout language is aggregate/analytical, distinct from individual-student entry screens.
 */

export function ExamAnalyticsScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";

  const [batches, setBatches] = useState<BatchRow[]>([]);
  const [batchId, setBatchId] = useState("");
  const [topics, setTopics] = useState<HeatmapTopic[]>([]);
  const [struggle, setStruggle] = useState<StruggleRow[]>([]);
  const [exams, setExams] = useState<ExamRow[]>([]);
  const [summary, setSummary] = useState<ExamSummary | null>(null);
  const [examId, setExamId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
        const [hm, st, ex] = await Promise.all([
          getTopicHeatmap(tenantId, useBatch),
          getStruggleList(tenantId, useBatch),
          listExams(tenantId, useBatch),
        ]);
        setTopics(hm.topics || []);
        setStruggle(st.students || []);
        setExams(ex.exams || []);
        if (!examId && ex.exams?.[0]) setExamId(ex.exams[0].id);
      }
    } catch (e) {
      setError((e as ApiError).detail || t("networkError"));
    } finally {
      setLoading(false);
    }
  }, [tenantId, batchId, examId, t]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!examId) {
      setSummary(null);
      return;
    }
    getExamSummary(tenantId, examId)
      .then(setSummary)
      .catch((e) => setError((e as ApiError).detail || t("genericError")));
  }, [examId, tenantId, t]);

  const maxMean = Math.max(1, ...topics.map((x) => x.mean_percentage));

  const nav = buildDeskNav(navigate, "exams");

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb="Owner / Desk · Exam analytics">
      <h2 className="view-title">Exam & batch analytics</h2>
      <p className="caption muted" style={{ marginBottom: 20 }}>
        Aggregate view — weakness heatmap and struggle list. Not an individual entry form.
      </p>

      <FormField id="an-batch" label="Batch">
        <SelectInput id="an-batch" value={batchId} onChange={(e) => setBatchId(e.target.value)}>
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

      <section className="analytics-grid">
        <Card variant="insight">
          <div className="eyebrow">Weakness heatmap · by topic</div>
          {topics.length === 0 && !loading && (
            <p className="caption muted">No topic results yet for this batch.</p>
          )}
          <ul className="heatmap">
            {topics.map((tp) => (
              <li key={tp.chapter_or_topic}>
                <div className="heatmap-label">
                  <span>{tp.chapter_or_topic}</span>
                  <span className="mono-data">{tp.mean_percentage}%</span>
                </div>
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
                <span className="caption">
                  n={tp.n} · min {tp.min_percentage}% · max {tp.max_percentage}%
                </span>
              </li>
            ))}
          </ul>
        </Card>

        <Card variant="insight">
          <div className="eyebrow">Students likely to struggle</div>
          {struggle.length === 0 && !loading && (
            <p className="caption muted">No students flagged for this batch.</p>
          )}
          <ul className="struggle-list">
            {struggle.map((s) => (
              <li key={s.student_id}>
                <span className="mono-data">{s.roll}</span>
                <span>{s.name}</span>
                <span className="caption">
                  avg {s.recent_avg_percentage ?? "—"}% · att {s.attended_days_this_month ?? "—"}d
                </span>
                <span className="badge badge-attendance-late" role="status">
                  {(s.reason || "flagged").replace(/_/g, " ")}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </section>

      <section style={{ marginTop: 28 }}>
        <div className="eyebrow">Single-exam summary</div>
        <FormField id="an-exam" label="Exam">
          <SelectInput id="an-exam" value={examId} onChange={(e) => setExamId(e.target.value)}>
            {exams.map((ex) => (
              <option key={ex.id} value={ex.id}>
                {ex.name} · {ex.exam_date}
              </option>
            ))}
          </SelectInput>
        </FormField>
        {summary && (
          <Card variant="featured">
            <div className="summary-stats">
              <div>
                <div className="caption">Present</div>
                <div className="stat-value mono-data">{summary.n_present ?? 0}</div>
              </div>
              <div>
                <div className="caption">Absent</div>
                <div className="stat-value mono-data">{summary.n_absent ?? 0}</div>
              </div>
              <div>
                <div className="caption">Mean %</div>
                <div className="stat-value mono-data">{summary.mean_percentage ?? "—"}</div>
              </div>
              <div>
                <div className="caption">Median %</div>
                <div className="stat-value mono-data">{summary.median_percentage ?? "—"}</div>
              </div>
            </div>
            {summary.section_averages && (
              <div style={{ marginTop: 16 }}>
                <div className="caption">Section averages</div>
                <ul className="section-avgs">
                  {Object.entries(summary.section_averages).map(([k, v]) => (
                    <li key={k}>
                      <span className="mono-data">{k}</span> · {v}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Card>
        )}
      </section>

      <style>{`
        .analytics-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
          gap: 20px;
        }
        .heatmap, .struggle-list, .section-avgs {
          list-style: none;
          margin: 12px 0 0;
          padding: 0;
        }
        .heatmap li { margin-bottom: 14px; }
        .heatmap-label {
          display: flex;
          justify-content: space-between;
          font-size: 14px;
          margin-bottom: 4px;
        }
        .heatmap-bar-track {
          height: 10px;
          background: var(--sage-100);
          border-radius: 100px;
          overflow: hidden;
        }
        .heatmap-bar {
          height: 100%;
          border-radius: 100px;
          transition: width var(--motion-slow) var(--easing-out);
        }
        .struggle-list li {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          align-items: center;
          padding: 8px 0;
          border-bottom: 1px solid var(--border);
          font-size: 14px;
        }
        .summary-stats {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 12px;
        }
        .stat-value {
          font-size: 22px;
          font-weight: 600;
          color: var(--ink);
        }
        @media (max-width: 760px) {
          .summary-stats { grid-template-columns: repeat(2, 1fr); }
        }
      `}</style>
    </AppShell>
  );
}
