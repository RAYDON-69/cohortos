import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { MobileShell } from "../../shell/MobileShell";
import { LanguageToggle } from "../../components/LanguageToggle";
import { Card } from "../../components/Card";
import { Button } from "../../components/Button";
import { FormField, TextInput } from "../../components/FormField";
import { AiBadge } from "../../components/Badge";
import { useLocale } from "../../i18n/LocaleContext";
import { listStudentThreads, getStudentThreadMessages, replyStudentThread, loadTokens } from "../../api/client"
import type { FlaggedThread, ThreadMessage, SolveResponse, ApiError } from "../../api/client"
import { loadStudentSession } from "./studentContext";
import "../../components/Button.css";
import "../../components/Card.css";
import "../../components/FormField.css";
import "../../components/Badge.css";
import "../../components/LanguageToggle.css";
import "../../shell/MobileShell.css";

/**
 * Student threads — Portion 21
 * Teacher take-over is visible with distinct visual treatment (SPEC §8.4).
 */

export function StudentThreadsScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";
  const session = loadStudentSession();

  const [threads, setThreads] = useState<FlaggedThread[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(params.get("id"));
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [reply, setReply] = useState("");
  const [lastSolve, setLastSolve] = useState<SolveResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadThreads = useCallback(async () => {
    if (!session.studentId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const res = await listStudentThreads(tenantId, session.studentId);
      setThreads(res.threads || []);
    } catch (e) {
      setError((e as ApiError).detail || t("networkError"));
    } finally {
      setLoading(false);
    }
  }, [tenantId, session.studentId, t]);

  useEffect(() => {
    loadThreads();
  }, [loadThreads]);

  useEffect(() => {
    if (!selectedId) {
      setMessages([]);
      return;
    }
    getStudentThreadMessages(tenantId, selectedId)
      .then((res) => setMessages(res.messages || []))
      .catch((e) => setError((e as ApiError).detail || t("genericError")));
  }, [selectedId, tenantId, t]);

  async function onReply() {
    if (!selectedId || !reply.trim() || !session.studentId) return;
    setSaving(true);
    setError(null);
    try {
      const res = await replyStudentThread(
        tenantId,
        selectedId,
        session.studentId,
        reply.trim()
      );
      setLastSolve(res);
      setReply("");
      const msgs = await getStudentThreadMessages(tenantId, selectedId);
      setMessages(msgs.messages || []);
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setSaving(false);
    }
  }

  const tabs = [
    { id: "home", label: t("navHome"), onClick: () => navigate("/student") },
    { id: "solve", label: t("navSolve"), onClick: () => navigate("/student/solve") },
    { id: "vault", label: t("navVault"), onClick: () => navigate("/student/vault") },
    { id: "results", label: t("navResults"), onClick: () => navigate("/student/results") },
  ];

  return (
    <MobileShell centreName={t("appName")} tabs={tabs} languageSlot={<LanguageToggle />}>
      <h1 className="view-title" style={{ fontSize: 22 }}>
        Threads
      </h1>
      <p className="caption muted" style={{ marginBottom: 16 }}>
        Your Solve conversations. Teacher take-overs appear clearly in the history.
      </p>

      {error && (
        <div className="warning-banner" role="alert">
          {error}
        </div>
      )}
      {loading && <p className="caption muted">{t("loadingView")}</p>}

      <div className="thread-stack">
        {threads.map((th) => (
          <button
            key={th.id}
            type="button"
            className={`thread-chip ${selectedId === th.id ? "active" : ""}`}
            onClick={() => setSelectedId(th.id)}
          >
            {th.title || th.subject || "Thread"}
          </button>
        ))}
        {!loading && threads.length === 0 && (
          <p className="caption muted">No threads yet — ask a question in Solve.</p>
        )}
      </div>

      {selectedId && (
        <Card style={{ marginTop: 16 } as React.CSSProperties}>
          <div className="eyebrow">Conversation</div>
          <div className="msg-stream">
            {messages.map((m) => {
              const role = m.role || "assistant";
              return (
                <div key={m.id || m.created_at} className={`smsg smsg-${role}`}>
                  <div className="smsg-role">
                    {role === "assistant" && "AI"}
                    {role === "user" && "You"}
                    {role === "teacher" && "Teacher took over"}
                    {role !== "assistant" && role !== "user" && role !== "teacher" && role}
                  </div>
                  <div className="smsg-body">
                    {m.content ||
                      [
                        (m as { answer_block?: string }).answer_block,
                        (m as { how_block?: string }).how_block,
                        (m as { why_block?: string }).why_block,
                      ]
                        .filter(Boolean)
                        .join("\n\n") ||
                      "—"}
                  </div>
                  {role === "assistant" && m.needs_review && (
                    <AiBadge status="confidence-low" label="Not confident — ask your teacher" />
                  )}
                </div>
              );
            })}
          </div>

          {lastSolve && lastSolve.needs_review && (
            <div className="not-confident" role="status">
              Not confident — ask your teacher.
            </div>
          )}

          <FormField id="sreply" label="Follow up">
            <TextInput
              id="sreply"
              value={reply}
              onChange={(e) => setReply(e.target.value)}
              placeholder="Ask a follow-up…"
            />
          </FormField>
          <Button
            variant="primary"
            onClick={() => void onReply()}
            loading={saving}
            disabled={!reply.trim()}
          >
            Send
          </Button>
        </Card>
      )}

      <style>{`
        .thread-stack {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        .thread-chip {
          border: 1px solid var(--border);
          background: var(--white);
          border-radius: 100px;
          padding: 8px 14px;
          font: inherit;
          font-size: 13px;
          cursor: pointer;
          min-height: 44px;
        }
        .thread-chip.active {
          border-color: var(--sage-700);
          background: var(--sage-100);
        }
        .msg-stream {
          display: grid;
          gap: 10px;
          max-height: 360px;
          overflow: auto;
          margin-bottom: 12px;
        }
        .smsg {
          border-radius: 12px;
          padding: 10px 12px;
          font-size: 14px;
        }
        .smsg-assistant {
          background: var(--sage-100);
          border: 1px solid var(--border);
        }
        .smsg-user {
          background: var(--white);
          border: 1px solid var(--border);
          margin-left: 16px;
        }
        .smsg-teacher {
          background: var(--peri-bg);
          border: 2px solid var(--peri-300);
        }
        .smsg-role {
          font-size: 11px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          margin-bottom: 4px;
          color: var(--slate-700);
        }
        .smsg-teacher .smsg-role {
          color: var(--peri-text);
        }
        .smsg-body { white-space: pre-wrap; line-height: 1.45; }
        .not-confident {
          background: var(--error-bg);
          border-radius: 8px;
          padding: 10px;
          margin-bottom: 12px;
          font-size: 14px;
        }
      `}</style>
    </MobileShell>
  );
}
