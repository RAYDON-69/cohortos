import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { buildDeskNav } from "../../nav/deskNav";
import { AppShell } from "../../shell/AppShell";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { DataTable } from "../../components/DataTable"
import type { Column } from "../../components/DataTable"
import { FormField, TextInput, SelectInput } from "../../components/FormField";
import { useLocale } from "../../i18n/LocaleContext";
import { ExamEntryErrorBanner, ExamEntryEmptyExams } from "./ExamEntryStatus";
import { listBatches, listExamTemplates, listExams, createExam, getExam, enterResult, getExamResults, completeExam, listStudentsApi, loadTokens } from "../../api/client"
import type { BatchRow, ExamTemplateRow, ExamRow, ExamResultRow, StudentRow, ApiError } from "../../api/client"

/**
 * Exam entry — Portion 16
 * Chapter (template, 3-component) and ad-hoc forms are visually distinct.
 * Result history is permanent/read-only in the results table (no edit affordance).
 */

type Mode = "chapter" | "adhoc";

export function ExamEntryScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";

  const [batches, setBatches] = useState<BatchRow[]>([]);
  const [templates, setTemplates] = useState<ExamTemplateRow[]>([]);
  const [exams, setExams] = useState<ExamRow[]>([]);
  const [students, setStudents] = useState<StudentRow[]>([]);
  const [mode, setMode] = useState<Mode>("chapter");
  const [batchId, setBatchId] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [name, setName] = useState("");
  const [examDate, setExamDate] = useState(new Date().toISOString().slice(0, 10));
  const [chapter, setChapter] = useState("");
  const [adhocMax, setAdhocMax] = useState(100);
  const [selectedExamId, setSelectedExamId] = useState<string | null>(null);
  const [selectedExam, setSelectedExam] = useState<ExamRow | null>(null);
  const [results, setResults] = useState<ExamResultRow[]>([]);
  const [entryStudent, setEntryStudent] = useState("");
  const [scores, setScores] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [b, tmpl, ex, st] = await Promise.all([
        listBatches(tenantId),
        listExamTemplates(tenantId),
        listExams(tenantId),
        listStudentsApi(tenantId),
      ]);
      setBatches(b.batches || []);
      setTemplates(tmpl.templates || []);
      setExams(ex.exams || []);
      setStudents(st.students || []);
      if (!batchId && b.batches?.[0]?.id) setBatchId(b.batches[0].id);
      const def = (tmpl.templates || []).find((x) => x.is_default) || tmpl.templates?.[0];
      if (!templateId && def) setTemplateId(def.id);
    } catch (e) {
      setError((e as ApiError).detail || t("networkError"));
    } finally {
      setLoading(false);
    }
  }, [tenantId, batchId, templateId, t]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!selectedExamId) {
      setSelectedExam(null);
      setResults([]);
      return;
    }
    (async () => {
      try {
        const [ex, res] = await Promise.all([
          getExam(tenantId, selectedExamId),
          getExamResults(tenantId, selectedExamId),
        ]);
        setSelectedExam(ex.exam);
        setResults(res.results || []);
        const sc: Record<string, string> = {};
        (ex.exam.sections || []).forEach((s) => {
          sc[s.key] = "";
        });
        setScores(sc);
      } catch (e) {
        setError((e as ApiError).detail || t("genericError"));
      }
    })();
  }, [selectedExamId, tenantId, t]);

  async function onCreate() {
    setSaving(true);
    setError(null);
    try {
      const body =
        mode === "chapter"
          ? {
              name: name || `${chapter || "Chapter"} exam`,
              exam_date: examDate,
              batch_id: batchId,
              template_id: templateId || undefined,
              chapter_or_topic: chapter,
              is_ad_hoc: false,
            }
          : {
              name: name || "Ad-hoc exam",
              exam_date: examDate,
              batch_id: batchId,
              is_ad_hoc: true,
              chapter_or_topic: chapter || "adhoc",
              sections: [
                {
                  key: "score",
                  name: "Score",
                  section_type: "custom",
                  max_marks: adhocMax,
                  question_count: 0,
                  duration_minutes: 0,
                  weight: 1,
                  immediate_result: false,
                },
              ],
            };
      const res = await createExam(tenantId, body);
      setSelectedExamId(res.exam_id);
      setName("");
      await load();
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setSaving(false);
    }
  }

  async function onEnterResult() {
    if (!selectedExamId || !entryStudent) return;
    setSaving(true);
    setError(null);
    try {
      const section_scores = Object.entries(scores)
        .filter(([, v]) => v !== "")
        .map(([key, v]) => ({ key, marks_obtained: Number(v) }));
      await enterResult(tenantId, selectedExamId, {
        student_id: entryStudent,
        section_scores,
      });
      const res = await getExamResults(tenantId, selectedExamId);
      setResults(res.results || []);
      setEntryStudent("");
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setSaving(false);
    }
  }

  const resultCols: Column<ExamResultRow>[] = [
    {
      key: "roll",
      header: "Roll",
      essential: true,
      render: (r) => <span className="mono-data">{r.roll || "—"}</span>,
    },
    {
      key: "percentage",
      header: "%",
      essential: true,
      render: (r) =>
        r.is_absent ? (
          <span className="badge badge-attendance-absent" role="status">
            Absent
          </span>
        ) : (
          <span className="mono-data">{r.percentage ?? "—"}</span>
        ),
    },
    {
      key: "total",
      header: "Total",
      essential: false,
      render: (r) => <span className="mono-data">{r.total_obtained ?? "—"}</span>,
    },
  ];

  const selectedTpl = templates.find((x) => x.id === templateId);

  const nav = buildDeskNav(navigate, "exams");

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb="Owner / Desk · Exam entry">
      <h2 className="view-title">Exam entry</h2>
      <p className="caption muted" style={{ marginBottom: 20 }}>
        Chapter exams use the 3-component template. Ad-hoc exams are a separate form and data shape.
        Results are permanent — no delete.
      </p>

      {error && <ExamEntryErrorBanner message={error} />}

      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        <Button
          size="sm"
          variant={mode === "chapter" ? "primary" : "outline"}
          onClick={() => setMode("chapter")}
        >
          Chapter exam (template)
        </Button>
        <Button
          size="sm"
          variant={mode === "adhoc" ? "primary" : "outline"}
          onClick={() => setMode("adhoc")}
        >
          Ad-hoc / custom exam
        </Button>
      </div>

      {mode === "chapter" ? (
        <Card variant="featured" className="exam-form-chapter">
          <div className="eyebrow">Chapter exam · 3-component structure</div>
          <p className="caption" style={{ marginBottom: 12 }}>
            Sections come from the template (MCQ + Physics Maths + CQ by default). Not free-form.
          </p>
          <FormField id="ch-batch" label="Batch">
            <SelectInput id="ch-batch" value={batchId} onChange={(e) => setBatchId(e.target.value)}>
              {batches.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.display_name || b.name || b.id}
                </option>
              ))}
            </SelectInput>
          </FormField>
          <FormField id="ch-tpl" label="Template">
            <SelectInput
              id="ch-tpl"
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
            >
              {templates.map((tpl) => (
                <option key={tpl.id} value={tpl.id}>
                  {tpl.name}
                  {tpl.is_default ? " (default)" : ""}
                </option>
              ))}
            </SelectInput>
          </FormField>
          {selectedTpl?.sections && (
            <ul className="section-preview">
              {selectedTpl.sections.map((s) => (
                <li key={s.key}>
                  <span className="mono-data">{s.section_type}</span> {s.name} · max{" "}
                  {s.max_marks}
                </li>
              ))}
            </ul>
          )}
          <FormField id="ch-chapter" label="Chapter / topic" required>
            <TextInput id="ch-chapter" value={chapter} onChange={(e) => setChapter(e.target.value)} />
          </FormField>
          <FormField id="ch-name" label="Exam name">
            <TextInput id="ch-name" value={name} onChange={(e) => setName(e.target.value)} />
          </FormField>
          <FormField id="ch-date" label="Date">
            <input
              id="ch-date"
              type="date"
              className="form-input"
              value={examDate}
              onChange={(e) => setExamDate(e.target.value)}
            />
          </FormField>
          <Button variant="primary" onClick={() => void onCreate()} loading={saving} disabled={!chapter}>
            Create chapter exam
          </Button>
        </Card>
      ) : (
        <Card className="exam-form-adhoc">
          <div className="eyebrow">Ad-hoc exam · single custom score</div>
          <p className="caption" style={{ marginBottom: 12 }}>
            Free-form sitting without the chapter template. Different data shape (one custom
            section).
          </p>
          <FormField id="ah-batch" label="Batch">
            <SelectInput id="ah-batch" value={batchId} onChange={(e) => setBatchId(e.target.value)}>
              {batches.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.display_name || b.name || b.id}
                </option>
              ))}
            </SelectInput>
          </FormField>
          <FormField id="ah-name" label="Exam name" required>
            <TextInput id="ah-name" value={name} onChange={(e) => setName(e.target.value)} />
          </FormField>
          <FormField id="ah-max" label="Max marks">
            <TextInput
              id="ah-max"
              type="number"
              value={String(adhocMax)}
              onChange={(e) => setAdhocMax(Number(e.target.value))}
            />
          </FormField>
          <FormField id="ah-date" label="Date">
            <input
              id="ah-date"
              type="date"
              className="form-input"
              value={examDate}
              onChange={(e) => setExamDate(e.target.value)}
            />
          </FormField>
          <Button
            variant="primary"
            onClick={() => void onCreate()}
            loading={saving}
            disabled={!name.trim()}
          >
            Create ad-hoc exam
          </Button>
        </Card>
      )}

      <section style={{ marginTop: 32 }}>
        <div className="eyebrow">Recent exams</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
          {exams.slice(0, 12).map((ex) => (
            <Button
              key={ex.id}
              size="sm"
              variant={selectedExamId === ex.id ? "primary" : "outline"}
              onClick={() => setSelectedExamId(ex.id)}
            >
              {ex.name} · {ex.exam_date}
              {ex.is_ad_hoc ? " · ad-hoc" : ""}
            </Button>
          ))}
          {exams.length === 0 && !loading && <ExamEntryEmptyExams />}
        </div>
      </section>

      {selectedExam && (
        <section style={{ marginTop: 28 }}>
          <Card>
            <div className="eyebrow">
              Enter results · {selectedExam.is_ad_hoc ? "ad-hoc" : "chapter"} · read-only history
              below
            </div>
            <p className="caption">
              {selectedExam.name} · {selectedExam.exam_date} · {selectedExam.status}
            </p>
            <FormField id="er-student" label="Student">
              <SelectInput
                id="er-student"
                value={entryStudent}
                onChange={(e) => setEntryStudent(e.target.value)}
              >
                <option value="">Select…</option>
                {students
                  .filter((s) => !selectedExam.batch_id || s.batch_id === selectedExam.batch_id)
                  .map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.roll} · {s.name}
                    </option>
                  ))}
              </SelectInput>
            </FormField>
            <div className="score-grid">
              {(selectedExam.sections || []).map((sec) => (
                <FormField key={sec.key} id={`sc-${sec.key}`} label={`${sec.name} (max ${sec.max_marks})`}>
                  <TextInput
                    id={`sc-${sec.key}`}
                    type="number"
                    value={scores[sec.key] ?? ""}
                    onChange={(e) => setScores((prev) => ({ ...prev, [sec.key]: e.target.value }))}
                  />
                </FormField>
              ))}
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <Button
                variant="primary"
                onClick={() => void onEnterResult()}
                loading={saving}
                disabled={!entryStudent}
              >
                Save result
              </Button>
              <Button
                variant="outline"
                onClick={async () => {
                  if (!selectedExamId) return;
                  await completeExam(tenantId, selectedExamId);
                  await load();
                  const ex = await getExam(tenantId, selectedExamId);
                  setSelectedExam(ex.exam);
                }}
              >
                Mark exam completed
              </Button>
            </div>
          </Card>

          <div style={{ marginTop: 16 }}>
            <div className="eyebrow">Result history (permanent · no edit)</div>
            <DataTable
              columns={resultCols}
              rows={results}
              rowKey={(r) => String(r.id || r.student_id)}
              emptyTitle="No results entered yet"
              emptyBody="Enter scores above. Records are never deleted."
            />
          </div>
        </section>
      )}

      <style>{`
        .section-preview {
          list-style: none;
          margin: 0 0 16px;
          padding: 8px 12px;
          background: var(--white);
          border: 1px solid var(--border);
          border-radius: 8px;
          font-size: 13px;
        }
        .section-preview li { padding: 4px 0; }
        .score-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
          gap: 12px;
        }
        .exam-form-chapter { margin-bottom: 8px; }
        .exam-form-adhoc { border-style: dashed; }
      `}</style>
    </AppShell>
  );
}
