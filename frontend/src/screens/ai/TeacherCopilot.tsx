/**
 * AI Teacher Copilot — primary chat surface (not buried only in Settings).
 * Uses /ai/query with grounded centre tools; BYO key from Settings → AI keys.
 */
import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { buildDeskNav } from "../../nav/deskNav";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { useTenant } from "../../hooks/useTenant";
import { apiRequest, tenantPath, type ApiError } from "../../api/client";

type Msg = { role: "user" | "assistant"; text: string; meta?: string };

export function TeacherCopilotScreen() {
  const navigate = useNavigate();
  const { tenantId } = useTenant();
  const [q, setQ] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([
    {
      role: "assistant",
      text: "Ask about your centre: student counts, batches, exams, or who may be struggling. Answers use your centre data; set a Groq or NIM key under Settings → Integrations for richer replies.",
    },
  ]);
  const [busy, setBusy] = useState(false);
  const [autoStatus, setAutoStatus] = useState<string | null>(null);
  const [actionLog, setActionLog] = useState<unknown[]>([]);

  async function ask() {
    if (!tenantId || !q.trim()) return;
    const question = q.trim();
    setQ("");
    setMsgs((m) => [...m, { role: "user", text: question }]);
    setBusy(true);
    try {
      const res = await apiRequest<{
        answer?: string;
        used_external_llm?: boolean;
        grounded?: Record<string, unknown>;
        tools_used?: unknown[];
      }>(tenantPath(tenantId, "/ai/query"), { method: "POST", body: { question } });
      const meta = res.used_external_llm
        ? "External model"
        : `Local grounded · students ${res.grounded?.student_count ?? "—"}`;
      setMsgs((m) => [...m, { role: "assistant", text: res.answer || "No answer", meta }]);
    } catch (e) {
      setMsgs((m) => [
        ...m,
        { role: "assistant", text: (e as ApiError)?.detail || "Request failed" },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function runFeeAutomation() {
    if (!tenantId) return;
    setAutoStatus("Running fee reminders…");
    try {
      const r = await apiRequest<{ notified?: number; type?: string }>(
        tenantPath(tenantId, "/automations/run-fee-reminders"),
        { method: "POST" }
      );
      setAutoStatus(`Fee reminders finished (${r.type || "ok"}).`);
      try {
        const lg = await apiRequest<{ log?: unknown[] }>(tenantPath(tenantId, "/automations/log"));
        setActionLog(lg.log || []);
      } catch { /* ignore */ }
    } catch (e) {
      setAutoStatus((e as ApiError)?.detail || "Automation failed");
    }
  }

  const nav = buildDeskNav(navigate, "ai");

  return (
    <AppShell brand="CohortOS" navItems={nav} crumb="Teacher Copilot">
      <div className="view" data-testid="teacher-copilot">
        <h1 className="view-title">Teacher Copilot</h1>
        <p className="caption muted">
          Centre-aware assistant. Keys: <Link to="/settings/ai-keys">AI API keys</Link>
        </p>
        <Card title="Action log" style={{ marginBottom: 16 }}>
          {actionLog.length === 0 ? (
            <p className="caption muted">Copilot and automation runs appear here.</p>
          ) : (
            <pre className="caption" style={{ maxHeight: 120, overflow: "auto", whiteSpace: "pre-wrap" }}>
              {JSON.stringify(actionLog.slice(-8).reverse(), null, 2)}
            </pre>
          )}
        </Card>
        <Card title="Automations" style={{ marginBottom: 16 }}>
          <p className="caption muted">Fee reminders can run on a schedule (server cron) or manually here.</p>
          <Button variant="outline" size="sm" onClick={() => void runFeeAutomation()}>
            Run fee reminders now
          </Button>
          {autoStatus && <p className="caption" role="status">{autoStatus}</p>}
        </Card>
        <div
          style={{
            border: "1px solid var(--border)",
            borderRadius: 8,
            minHeight: 280,
            padding: 12,
            marginBottom: 12,
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          {msgs.map((m, i) => (
            <div key={i} style={{ alignSelf: m.role === "user" ? "flex-end" : "flex-start", maxWidth: "90%" }}>
              <div
                style={{
                  background: m.role === "user" ? "var(--peri-bg)" : "var(--surface-2)",
                  padding: "8px 12px",
                  borderRadius: 8,
                }}
              >
                {m.text}
              </div>
              {m.meta && <div className="caption muted">{m.meta}</div>}
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            className="form-input"
            style={{ flex: 1 }}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void ask()}
            placeholder="e.g. How many students? List exams named KINETICS"
            disabled={busy}
          />
          <Button variant="primary" onClick={() => void ask()} disabled={busy || !q.trim()}>
            Ask
          </Button>
        </div>
      </div>
    </AppShell>
  );
}
