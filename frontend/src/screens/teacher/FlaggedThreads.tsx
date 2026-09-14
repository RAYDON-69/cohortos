import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { AiBadge } from "../../components/Badge";
import { FormField, TextInput } from "../../components/FormField";
import { useLocale } from "../../i18n/LocaleContext";
import { listFlaggedThreads, getThreadMessages, takeOverThread, loadTokens } from "../../api/client"
import type { FlaggedThread, ThreadMessage, ApiError } from "../../api/client"
import "../../components/Button.css";
import "../../components/Card.css";
import "../../components/Badge.css";
import "../../components/FormField.css";
import "../../shell/AppShell.css";

/**
 * Flagged threads + take-over — Portion 19
 * Ranking has "why flagged" affordance.
 * Full history with distinct AI / student / teacher treatments.
 */

export function FlaggedThreadsScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";

  const [threads, setThreads] = useState<FlaggedThread[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [threadMeta, setThreadMeta] = useState<FlaggedThread | null>(null);
  const [reply, setReply] = useState("");
  const [whyOpen, setWhyOpen] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listFlaggedThreads(tenantId);
      setThreads(res.threads || []);
    } catch (e) {
      setError((e as ApiError).detail || t("networkError"));
    } finally {
      setLoading(false);
    }
  }, [tenantId, t]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!selectedId) {
      setMessages([]);
      setThreadMeta(null);
      return;
    }
    getThreadMessages(tenantId, selectedId)
      .then((res) => {
        setMessages(res.messages || []);
        setThreadMeta(res.thread);
      })
      .catch((e) => setError((e as ApiError).detail || t("genericError")));
  }, [selectedId, tenantId, t]);

  async function onTakeOver() {
    if (!selectedId || !reply.trim()) return;
    setSaving(true);
    try {
      await takeOverThread(
        tenantId,
        selectedId,
        reply.trim(),
        threadMeta?.student_id || ""
      );
      setReply("");
      const res = await getThreadMessages(tenantId, selectedId);
      setMessages(res.messages || []);
      await load();
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setSaving(false);
    }
  }

  function whyFlagged(th: FlaggedThread): string {
    const parts: string[] = [];
    if (th.min_confidence != null) {
      parts.push(`lowest AI confidence ${Number(th.min_confidence).toFixed(2)}`);
    }
    if (th.priority != null) {
      parts.push(`priority score ${Number(th.priority).toFixed(2)} (confidence × activity)`);
    }
    if (th.message_count != null) {
      parts.push(`${th.message_count} messages in thread`);
    }
    parts.push("ranked for teacher attention — exam proximity may raise impact when available");
    return parts.join(" · ");
  }

  const nav = [
    { id: "review", label: t("navReview"), onClick: () => navigate("/teacher/review") },
    { id: "threads", label: t("navThreads"), active: true },
  ];

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb="Teacher · Flagged threads">
      <h2 className="view-title">Flagged threads</h2>
      <p className="caption muted" style={{ marginBottom: 20 }}>
        Ranked for review. Open a thread for full history, then take over.
      </p>

      {error && (
        <div className="warning-banner" role="alert">
          {error}
        </div>
      )}

      <div className="threads-layout">
        <div className="thread-list">
          {loading && <p className="caption muted">{t("loadingView")}</p>}
          {!loading && threads.length === 0 && (
            <Card>
              <p>No flagged threads.</p>
            </Card>
          )}
          {threads.map((th) => (
            <Card
              key={th.id}
              variant={selectedId === th.id ? "featured" : "queue-flagged"}
              onClick={() => setSelectedId(th.id)}
            >
              <div className="eyebrow">{th.subject || th.title || "Thread"}</div>
              <div className="mono-data caption">{th.student_id}</div>
              <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                {th.min_confidence != null && (
                  <AiBadge
                    status={
                      Number(th.min_confidence) < 0.65
                        ? "confidence-low"
                        : "confidence-medium"
                    }
                    label={`conf ${Number(th.min_confidence).toFixed(2)}`}
                  />
                )}
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={(e) => {
                    e.stopPropagation();
                    setWhyOpen((s) => ({ ...s, [th.id]: !s[th.id] }));
                  }}
                >
                  Why flagged?
                </Button>
              </div>
              {whyOpen[th.id] && (
                <p className="caption" style={{ marginTop: 8 }}>
                  {whyFlagged(th)}
                </p>
              )}
            </Card>
          ))}
        </div>

        <div className="thread-detail">
          {!selectedId && (
            <Card>
              <p className="caption muted">Select a flagged thread to see full history.</p>
            </Card>
          )}
          {selectedId && (
            <Card>
              <div className="eyebrow">Full conversation</div>
              <div className="message-stream">
                {messages.map((m) => {
                  const role = m.role || "assistant";
                  return (
                    <div key={m.id || m.created_at} className={`msg msg-${role}`}>
                      <div className="msg-role">
                        {role === "assistant" && "AI"}
                        {role === "user" && "Student"}
                        {role === "teacher" && "Teacher took over"}
                        {role !== "assistant" && role !== "user" && role !== "teacher" && role}
                      </div>
                      <div className="msg-body">{m.content}</div>
                      {role === "assistant" && (
                        <div className="msg-meta">
                          {m.grounded === false ||
                          (m.needs_review && !(m.source_chunks && m.source_chunks.length)) ? (
                            <AiBadge status="ungrounded" label={t("ungrounded")} />
                          ) : (
                            m.source_chunks &&
                            m.source_chunks.length > 0 && (
                              <AiBadge status="grounded" label={t("grounded")} />
                            )
                          )}
                          {m.confidence != null && (
                            <span className="caption mono-data">
                              conf {Number(m.confidence).toFixed(2)}
                            </span>
                          )}
                        </div>
                      )}
                      {m.source_chunks && m.source_chunks.length > 0 && (
                        <div className="inline-chunks">
                          {m.source_chunks.map((c, i) => (
                            <blockquote key={i}>{c.text || JSON.stringify(c)}</blockquote>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
                {messages.length === 0 && (
                  <p className="caption muted">No messages in this thread yet.</p>
                )}
              </div>

              <div style={{ marginTop: 16, borderTop: "1px solid var(--border)", paddingTop: 16 }}>
                <FormField id="takeover" label="Take over — teacher reply">
                  <TextInput
                    id="takeover"
                    value={reply}
                    onChange={(e) => setReply(e.target.value)}
                    placeholder="Write as the teacher…"
                  />
                </FormField>
                <Button
                  variant="primary"
                  onClick={() => void onTakeOver()}
                  loading={saving}
                  disabled={!reply.trim()}
                >
                  Take over thread
                </Button>
              </div>
            </Card>
          )}
        </div>
      </div>

      <style>{`
        .threads-layout {
          display: grid;
          grid-template-columns: minmax(240px, 1fr) minmax(280px, 1.4fr);
          gap: 20px;
        }
        @media (max-width: 760px) {
          .threads-layout { grid-template-columns: 1fr; }
        }
        .thread-list { display: grid; gap: 12px; align-content: start; }
        .message-stream { display: grid; gap: 12px; max-height: 480px; overflow: auto; }
        .msg {
          border-radius: 12px;
          padding: 12px 14px;
          font-size: 14px;
        }
        .msg-assistant {
          background: var(--sage-100);
          border: 1px solid var(--border);
        }
        .msg-user {
          background: var(--white);
          border: 1px solid var(--border);
          margin-left: 24px;
        }
        .msg-teacher {
          background: var(--peri-bg);
          border: 2px solid var(--peri-300);
        }
        .msg-role {
          font-size: 11px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          color: var(--slate-700);
          margin-bottom: 4px;
        }
        .msg-teacher .msg-role { color: var(--peri-text); }
        .msg-meta { display: flex; gap: 8px; margin-top: 6px; align-items: center; }
        .inline-chunks blockquote {
          margin: 6px 0 0;
          padding: 6px 10px;
          border-left: 3px solid var(--sage-300);
          font-size: 12px;
          color: var(--slate-700);
        }
      `}</style>
    </AppShell>
  );
}
