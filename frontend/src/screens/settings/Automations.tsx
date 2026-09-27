/**
 * Configurable automations — n8n-style trigger / condition / action builder
 * wired to the existing backend rules engine.
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

type Rule = {
  id?: string;
  name?: string;
  enabled?: boolean;
  trigger?: { type?: string };
  conditions?: { field?: string; op?: string; value?: string }[];
  actions?: { type?: string; params?: Record<string, unknown> }[];
};

const TRIGGERS = [
  { value: "manual", label: "Manual (run from desk)" },
  { value: "schedule.daily", label: "Schedule — daily" },
  { value: "schedule.weekly", label: "Schedule — weekly" },
  { value: "event.fee_overdue", label: "Event — fee overdue" },
  { value: "event.attendance_marked", label: "Event — attendance marked" },
  { value: "event.admission_created", label: "Event — admission created" },
];

const CONDITIONS = [
  { value: "", label: "No condition (always)" },
  { value: "fee.days_overdue>=7", label: "Fee days overdue ≥ 7" },
  { value: "fee.days_overdue>=14", label: "Fee days overdue ≥ 14" },
  { value: "attendance.rate<75", label: "Attendance rate < 75%" },
  { value: "student.status=active", label: "Student is active" },
];

const ACTIONS = [
  { value: "fee_reminder", label: "Send fee reminder" },
  { value: "fee_reminder_escalation", label: "Escalate fee reminder" },
  { value: "notify_owner", label: "Notify centre owner" },
  { value: "notify_guardian", label: "Notify guardian" },
  { value: "log_only", label: "Log only (dry run)" },
];

function parseCondition(raw: string): { field?: string; op?: string; value?: string } | null {
  if (!raw) return null;
  const m = raw.match(/^([a-z._]+)(>=|<=|==|=|<|>)(.+)$/i);
  if (!m) return { field: raw, op: "eq", value: "true" };
  return { field: m[1], op: m[2] === "==" ? "=" : m[2], value: m[3] };
}

export function AutomationsScreen() {
  const navigate = useNavigate();
  const { tenantId } = useTenant();
  const [rules, setRules] = useState<Rule[]>([]);
  const [log, setLog] = useState<unknown[]>([]);
  const [name, setName] = useState("Fee overdue reminder");
  const [trigger, setTrigger] = useState("manual");
  const [condition, setCondition] = useState("fee.days_overdue>=7");
  const [action, setAction] = useState("fee_reminder");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!tenantId) return;
    try {
      const [r, l] = await Promise.all([
        apiRequest<{ rules?: Rule[] }>(tenantPath(tenantId, "/automations/rules")),
        apiRequest<{ log?: unknown[] }>(tenantPath(tenantId, "/automations/log")),
      ]);
      setRules(r.rules || []);
      setLog(l.log || []);
    } catch (e) {
      setError((e as ApiError)?.detail || "Failed to load automations");
    }
  }, [tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function createRule() {
    if (!tenantId || !name.trim()) return;
    setMsg(null);
    setError(null);
    const cond = parseCondition(condition);
    try {
      await apiRequest(tenantPath(tenantId, "/automations/rules"), {
        method: "POST",
        body: {
          name: name.trim(),
          enabled: true,
          trigger: { type: trigger },
          conditions: cond ? [cond] : [],
          actions: [{ type: action, params: {} }],
        },
      });
      setMsg("Automation saved");
      await load();
    } catch (e) {
      setError((e as ApiError)?.detail || "Save failed");
    }
  }

  async function toggle(rule: Rule, enabled: boolean) {
    if (!tenantId || !rule.id) return;
    await apiRequest(tenantPath(tenantId, `/automations/rules/${rule.id}/enable`), {
      method: "POST",
      body: { enabled },
    });
    await load();
  }

  async function run(rule: Rule) {
    if (!tenantId || !rule.id) return;
    const res = await apiRequest(tenantPath(tenantId, `/automations/rules/${rule.id}/run`), {
      method: "POST",
      body: {},
    });
    setMsg(`Ran: ${JSON.stringify(res).slice(0, 160)}`);
    await load();
  }

  const nav = buildDeskNav(navigate, "settings");

  return (
    <AppShell brand="CohortOS" navItems={nav} crumb="Automations">
      <div className="view" data-testid="automations">
        <h1 className="view-title">Automations</h1>
        <p className="caption muted">
          Build rules with a trigger, optional condition, and action — same model as the backend
          engine (n8n-style blocks).
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
        <Card title="New automation">
          <FormField id="aname" label="Name">
            <TextInput id="aname" value={name} onChange={(e) => setName(e.target.value)} />
          </FormField>
          <FormField id="atrigger" label="Trigger">
            <select
              id="atrigger"
              className="input"
              value={trigger}
              onChange={(e) => setTrigger(e.target.value)}
              aria-label="Trigger"
            >
              {TRIGGERS.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </FormField>
          <FormField id="acond" label="Condition">
            <select
              id="acond"
              className="input"
              value={condition}
              onChange={(e) => setCondition(e.target.value)}
              aria-label="Condition"
            >
              {CONDITIONS.map((c) => (
                <option key={c.value || "none"} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
          </FormField>
          <FormField id="aaction" label="Action">
            <select
              id="aaction"
              className="input"
              value={action}
              onChange={(e) => setAction(e.target.value)}
              aria-label="Action"
            >
              {ACTIONS.map((a) => (
                <option key={a.value} value={a.value}>
                  {a.label}
                </option>
              ))}
            </select>
          </FormField>
          <Button variant="primary" onClick={() => void createRule()}>
            Save automation
          </Button>
        </Card>
        <div style={{ marginTop: 16, display: "grid", gap: 12 }}>
          {rules.map((r) => (
            <Card key={r.id} title={r.name || r.id}>
              <p className="caption muted">
                Trigger: {r.trigger?.type || "—"} · Action:{" "}
                {(r.actions || []).map((a) => a.type).join(", ") || "—"} ·{" "}
                {r.enabled ? "Enabled" : "Disabled"}
              </p>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <Button variant="secondary" onClick={() => void toggle(r, !r.enabled)}>
                  {r.enabled ? "Disable" : "Enable"}
                </Button>
                <Button variant="secondary" onClick={() => void run(r)}>
                  Run now
                </Button>
              </div>
            </Card>
          ))}
        </div>
        {log.length > 0 && (
          <Card title="Recent runs">
            <pre className="caption" style={{ whiteSpace: "pre-wrap", maxHeight: 240, overflow: "auto" }}>
              {JSON.stringify(log.slice(0, 12), null, 2)}
            </pre>
          </Card>
        )}
      </div>
    </AppShell>
  );
}
