/**
 * P25 Class workspace — schedule sessions, open Jitsi join links, post notices.
 */
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { buildDeskNav } from "../../nav/deskNav";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { FormField, TextInput } from "../../components/FormField";
import { useTenant } from "../../hooks/useTenant";
import { apiRequest, tenantPath, type ApiError } from "../../api/client";

type Session = {
  id: string;
  batch_id: string;
  title: string;
  starts_at?: string;
  status?: string;
};

export function ClassWorkspaceScreen() {
  const navigate = useNavigate();
  const { tenantId } = useTenant();
  const [batchId, setBatchId] = useState("");
  const [title, setTitle] = useState("Class session");
  const [mode, setMode] = useState<"interactive" | "broadcast">("broadcast");
  const [broadcastUrl, setBroadcastUrl] = useState("");
  const [recordingUrl, setRecordingUrl] = useState("");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [joinUrl, setJoinUrl] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!tenantId) return;
    try {
      const q = batchId ? `?batch_id=${encodeURIComponent(batchId)}` : "";
      const r = await apiRequest<{ sessions?: Session[] }>(
        tenantPath(tenantId, `/classes/sessions${q}`)
      );
      setSessions(r.sessions || []);
    } catch (e) {
      setError((e as ApiError)?.detail || "Load failed");
    }
  }, [tenantId, batchId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function create() {
    if (!tenantId || !batchId) {
      setError("Batch id required");
      return;
    }
    setError(null);
    try {
      await apiRequest(tenantPath(tenantId, "/classes/sessions"), {
        method: "POST",
        body: { batch_id: batchId, title, mode, broadcast_url: broadcastUrl },
      });
      setMsg("Session created");
      await load();
    } catch (e) {
      setError((e as ApiError)?.detail || "Create failed");
    }
  }

  async function join(sessionId: string, role: string) {
    if (!tenantId) return;
    setError(null);
    try {
      const r = await apiRequest<{ join_url?: string }>(
        tenantPath(tenantId, `/classes/sessions/${sessionId}/join`),
        { method: "POST", body: { role, display_name: role === "moderator" ? "Teacher" : "Student" } }
      );
      setJoinUrl(r.join_url || null);
      if (r.join_url) window.open(r.join_url, "_blank", "noopener,noreferrer");
    } catch (e) {
      setError((e as ApiError)?.detail || "Join failed");
    }
  }

  async function postNotice(sessionId: string) {
    if (!tenantId || !notice.trim()) return;
    try {
      await apiRequest(tenantPath(tenantId, `/classes/sessions/${sessionId}/notices`), {
        method: "POST",
        body: { body: notice },
      });
      setMsg("Notice posted");
      setNotice("");
    } catch (e) {
      setError((e as ApiError)?.detail || "Notice failed");
    }
  }

  const nav = buildDeskNav(navigate, "settings");
  return (
    <AppShell brand="CohortOS" navItems={nav} crumb="Classes">
      <div className="view" data-testid="class-workspace">
        <h1 className="view-title">Class workspace</h1>
        <p className="caption muted">
          Schedule a batch session and open a Jitsi room. Room names are opaque (no student names).
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
        <Card title="New session">
          <FormField id="cbatch" label="Batch id">
            <TextInput id="cbatch" value={batchId} onChange={(e) => setBatchId(e.target.value)} />
          </FormField>
          <FormField id="ctitle" label="Title">
            <TextInput id="ctitle" value={title} onChange={(e) => setTitle(e.target.value)} />
          </FormField>
          <FormField id="cmode" label="Mode">
            <select
              id="cmode"
              className="input"
              value={mode}
              onChange={(e) => setMode(e.target.value as "interactive" | "broadcast")}
            >
              <option value="broadcast">Broadcast (YouTube / FB Live — low cost)</option>
              <option value="interactive">Interactive (Jitsi)</option>
            </select>
          </FormField>
          {mode === "broadcast" && (
            <FormField id="curl" label="Stream URL">
              <TextInput
                id="curl"
                value={broadcastUrl}
                onChange={(e) => setBroadcastUrl(e.target.value)}
                placeholder="https://youtube.com/... or Facebook Live"
              />
            </FormField>
          )}
          <Button variant="primary" onClick={() => void create()}>
            Create session
          </Button>
        </Card>
        <Card title="Sessions">
          <ul data-testid="class-session-list">
            {sessions.map((s) => (
              <li key={s.id} style={{ marginBottom: 12 }}>
                <strong>{s.title}</strong> — {s.status} — batch {s.batch_id}
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 4 }}>
                  <Button variant="primary" onClick={() => void join(s.id, "moderator")}>
                    Teacher join
                  </Button>
                  <Button variant="secondary" onClick={() => void join(s.id, "participant")}>
                    Student join link
                  </Button>
                  <Button variant="ghost" onClick={() => void postNotice(s.id)}>
                    Post notice
                  </Button>
                </div>
              </li>
            ))}
          </ul>
          <FormField id="cnotice" label="Notice text">
            <TextInput id="cnotice" value={notice} onChange={(e) => setNotice(e.target.value)} />
          </FormField>
          {joinUrl && (
            <p className="caption" data-testid="class-join-url">
              Last join URL: {joinUrl}
            </p>
          )}
        </Card>
      </div>
    </AppShell>
  );
}
