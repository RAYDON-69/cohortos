/**
 * AI Tutor — answers grounded on this student's batch Vault only, with citations.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { buildDeskNav } from "../../nav/deskNav";
import { Button } from "../../components/Button";
import { useTenant } from "../../hooks/useTenant";
import { apiRequest, tenantPath, type ApiError } from "../../api/client";
import "../../shell/AppShell.css";

type Cite = { resource_id?: string; title?: string; excerpt?: string };

export function StudentTutorScreen() {
  const navigate = useNavigate();
  const { tenantId } = useTenant();
  const [studentId, setStudentId] = useState("");
  const [batchId, setBatchId] = useState("");
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [cites, setCites] = useState<Cite[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function ask() {
    if (!tenantId || !q.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await apiRequest<{
        answer?: string;
        citations?: Cite[];
        grounded?: boolean;
      }>(tenantPath(tenantId, "/tutor/query"), {
        method: "POST",
        body: { question: q.trim(), student_id: studentId || undefined, batch_id: batchId || undefined },
      });
      setAnswer(res.answer || "");
      setCites(res.citations || []);
    } catch (e) {
      setError((e as ApiError)?.detail || "Tutor request failed");
    } finally {
      setBusy(false);
    }
  }

  const nav = buildDeskNav(navigate, "ai");

  return (
    <AppShell brand="CohortOS" navItems={nav} crumb="AI Tutor">
      <div className="view" data-testid="student-tutor">
        <h1 className="view-title">AI Tutor</h1>
        <p className="caption muted">
          Answers use only your batch&apos;s vault documents (notes, papers). Sources are listed below each answer.
        </p>
        <label className="caption">
          Student id (optional)
          <input className="form-input" value={studentId} onChange={(e) => setStudentId(e.target.value)} />
        </label>
        <label className="caption">
          Batch id (optional if student known)
          <input className="form-input" value={batchId} onChange={(e) => setBatchId(e.target.value)} />
        </label>
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <input
            className="form-input"
            style={{ flex: 1 }}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Ask about a topic from your notes…"
            disabled={busy}
          />
          <Button variant="primary" onClick={() => void ask()} disabled={busy || !q.trim()}>
            Ask
          </Button>
        </div>
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}
        {answer && (
          <div style={{ marginTop: 16 }} data-testid="tutor-answer">
            <p style={{ whiteSpace: "pre-wrap" }}>{answer}</p>
            {cites.length > 0 && (
              <div className="caption" style={{ marginTop: 12 }}>
                <strong>Sources</strong>
                <ol>
                  {cites.map((c, i) => (
                    <li key={i}>
                      {c.title || c.resource_id}: {(c.excerpt || "").slice(0, 120)}
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}
