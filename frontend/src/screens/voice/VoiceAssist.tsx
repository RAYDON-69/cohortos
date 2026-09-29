/**
 * P24 Assisted voice desk — draft scripts + log call summaries.
 * Software does not autodial; staff places the call.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { buildDeskNav } from "../../nav/deskNav";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { FormField, TextInput } from "../../components/FormField";
import { useTenant } from "../../hooks/useTenant";
import { apiRequest, tenantPath, type ApiError } from "../../api/client";

export function VoiceAssistScreen() {
  const navigate = useNavigate();
  const { tenantId } = useTenant();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [purpose, setPurpose] = useState("fee_reminder");
  const [script, setScript] = useState("");
  const [scriptId, setScriptId] = useState("");
  const [notes, setNotes] = useState("");
  const [summary, setSummary] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function genScript() {
    if (!tenantId) return;
    setError(null);
    try {
      const r = await apiRequest<{ script?: string; script_id?: string }>(
        tenantPath(tenantId, "/voice/script"),
        {
          method: "POST",
          body: { student_name: name, phone, purpose, language: "bn" },
        }
      );
      setScript(r.script || "");
      setScriptId(r.script_id || "");
    } catch (e) {
      setError((e as ApiError)?.detail || "Script failed");
    }
  }

  async function logSummary() {
    if (!tenantId) return;
    setError(null);
    try {
      const r = await apiRequest<{ summary?: string }>(tenantPath(tenantId, "/voice/summarize"), {
        method: "POST",
        body: { call_notes: notes, student_name: name, purpose },
      });
      setSummary(r.summary || "");
      setMsg("Summary saved");
    } catch (e) {
      setError((e as ApiError)?.detail || "Summary failed");
    }
  }

  async function humanCall() {
    if (!tenantId) return;
    setError(null);
    const human_action_id = crypto.randomUUID();
    try {
      const r = await apiRequest<{ placed?: boolean; message?: string }>(
        tenantPath(tenantId, "/voice/request-call"),
        {
          method: "POST",
          body: { phone, script_id: scriptId, script, human_action_id },
        }
      );
      setMsg(
        r.placed
          ? "Provider accepted call request"
          : r.message || "Place the call manually using the script (software did not dial)."
      );
    } catch (e) {
      setError((e as ApiError)?.detail || "Request failed");
    }
  }

  const nav = buildDeskNav(navigate, "settings");
  return (
    <AppShell brand="CohortOS" navItems={nav} crumb="Voice assist">
      <div className="view" data-testid="voice-assist">
        <h1 className="view-title">Voice assist</h1>
        <p className="caption muted">
          Draft a script, call from your phone, then save a summary. The app does not autodial.
        </p>
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}
        {msg && (
          <p className="caption" role="status">
            {msg}
          </p>
        )}
        <Card title="Call script">
          <FormField id="vname" label="Student name">
            <TextInput id="vname" value={name} onChange={(e) => setName(e.target.value)} />
          </FormField>
          <FormField id="vphone" label="Phone (01XXXXXXXXX)">
            <TextInput id="vphone" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </FormField>
          <FormField id="vpur" label="Purpose">
            <select
              id="vpur"
              className="input"
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
            >
              <option value="fee_reminder">Fee reminder</option>
              <option value="attendance">Attendance follow-up</option>
              <option value="exam">Exam notice</option>
            </select>
          </FormField>
          <Button variant="primary" onClick={() => void genScript()}>
            Generate script
          </Button>
          {script && (
            <pre className="caption" style={{ whiteSpace: "pre-wrap", marginTop: 12 }} data-testid="voice-script">
              {script}
            </pre>
          )}
          <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Button variant="secondary" onClick={() => void humanCall()} disabled={!script}>
              Log human call action
            </Button>
          </div>
        </Card>
        <Card title="After the call">
          <FormField id="vnotes" label="Call notes">
            <TextInput id="vnotes" value={notes} onChange={(e) => setNotes(e.target.value)} />
          </FormField>
          <Button variant="primary" onClick={() => void logSummary()}>
            Save summary
          </Button>
          {summary && (
            <p className="caption" data-testid="voice-summary" style={{ marginTop: 12 }}>
              {summary}
            </p>
          )}
        </Card>
      </div>
    </AppShell>
  );
}
