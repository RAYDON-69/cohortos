import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { MobileShell } from "../../shell/MobileShell";
import { LanguageToggle } from "../../components/LanguageToggle";
import { Card } from "../../components/Card";
import { Button } from "../../components/Button";
import { FormField, TextInput } from "../../components/FormField";
import { AiBadge } from "../../components/Badge";
import { useLocale } from "../../i18n/LocaleContext";
import { solveAsk, loadTokens } from "../../api/client"
import type { SolveResponse, ApiError } from "../../api/client"
import { loadStudentSession } from "./studentContext";
import "../../components/FormField.css";
import "../../components/Badge.css";
import "../../components/LanguageToggle.css";
import "../../shell/MobileShell.css";

/**
 * CohortOS Solve — Portion 21
 * Fixed three-block layout: Answer / How / Why (SPEC §9.1).
 * Self-verification / low confidence shown honestly — never hidden.
 */

export function StudentSolveScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";
  const session = loadStudentSession();

  const [question, setQuestion] = useState("");
  const [subject, setSubject] = useState("");
  const [result, setResult] = useState<SolveResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onAsk() {
    if (!question.trim() || !session.studentId) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await solveAsk(tenantId, {
        student_id: session.studentId,
        question: question.trim(),
        subject: subject || undefined,
        thread_id: result?.thread_id,
      });
      setResult(res);
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setLoading(false);
    }
  }

  const tabs = [
    { id: "home", label: t("navHome"), onClick: () => navigate("/student") },
    { id: "solve", label: t("navSolve"), active: true },
    { id: "vault", label: t("navVault"), onClick: () => navigate("/student/vault") },
    { id: "results", label: t("navResults"), onClick: () => navigate("/student/results") },
  ];

  const notConfident =
    result &&
    (result.needs_review ||
      (result.confidence != null && result.confidence < 0.65) ||
      result.grounded === false);

  return (
    <MobileShell centreName={t("appName")} tabs={tabs} languageSlot={<LanguageToggle />}>
      <h1 className="view-title" style={{ fontSize: 22 }}>
        {t("navSolve")}
      </h1>
      <p className="caption muted" style={{ marginBottom: 16 }}>
        Answer · How · Why — structured help, not free-form chat.
      </p>

      {!session.studentId && (
        <div className="warning-banner" role="status">
          Link your admission on Home before asking questions.
        </div>
      )}

      {error && (
        <div className="warning-banner" role="alert">
          {error}
        </div>
      )}

      <Card>
        <FormField id="sq-subject" label="Subject">
          <TextInput
            id="sq-subject"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Physics"
          />
        </FormField>
        <FormField id="sq-q" label="Your question" required>
          <textarea
            id="sq-q"
            className="form-input"
            rows={3}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask about a problem or concept…"
          />
        </FormField>
        <Button
          variant="primary"
          onClick={() => void onAsk()}
          loading={loading}
          disabled={!question.trim() || !session.studentId}
        >
          Ask
        </Button>
      </Card>

      {result && (
        <div className="solve-blocks">
          {result.ok === false && (
            <div className="warning-banner" role="status">
              {result.message || result.error || "Could not answer right now."}
            </div>
          )}

          {notConfident && (
            <div className="not-confident" role="status">
              <AiBadge status="confidence-low" label={t("confidenceLow")} />
              <p>
                Not confident — ask your teacher.
                {result.review_reason ? ` (${result.review_reason})` : ""}
              </p>
            </div>
          )}

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {result.grounded === true && (
              <AiBadge status="grounded" label={t("grounded")} />
            )}
            {result.grounded === false && (
              <AiBadge status="ungrounded" label={t("ungrounded")} />
            )}
            {result.confidence != null && result.confidence >= 0.65 && result.confidence < 0.85 && (
              <AiBadge status="confidence-medium" label={t("confidenceMedium")} />
            )}
          </div>

          {/* Fixed three-block layout — SPEC §9.1 */}
          <section className="solve-block" aria-labelledby="blk-answer">
            <h2 id="blk-answer" className="solve-block-title">
              Answer
            </h2>
            <div className="solve-block-body">{result.answer || "—"}</div>
          </section>
          <section className="solve-block" aria-labelledby="blk-how">
            <h2 id="blk-how" className="solve-block-title">
              How
            </h2>
            <div className="solve-block-body">{result.how || "—"}</div>
          </section>
          <section className="solve-block" aria-labelledby="blk-why">
            <h2 id="blk-why" className="solve-block-title">
              Why
            </h2>
            <div className="solve-block-body">{result.why || "—"}</div>
          </section>

          {result.thread_id && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => navigate(`/student/threads?id=${result.thread_id}`)}
            >
              Open thread
            </Button>
          )}
        </div>
      )}

      <style>{`
        .solve-blocks {
          display: grid;
          gap: 14px;
          margin-top: 20px;
        }
        .solve-block {
          background: var(--white);
          border: 1px solid var(--border);
          border-radius: 12px;
          padding: 14px 16px;
          box-shadow: var(--shadow);
        }
        .solve-block-title {
          margin: 0 0 8px;
          font-size: 12px;
          font-weight: 700;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          color: var(--slate-700);
        }
        .solve-block-body {
          font-size: 15px;
          line-height: 1.55;
          color: var(--ink);
          white-space: pre-wrap;
        }
        .not-confident {
          display: flex;
          flex-direction: column;
          gap: 8px;
          background: var(--error-bg);
          border: 1px solid var(--error);
          border-radius: 12px;
          padding: 12px 14px;
          font-size: 14px;
          color: var(--ink);
        }
        .not-confident p { margin: 0; }
      `}</style>
    </MobileShell>
  );
}
