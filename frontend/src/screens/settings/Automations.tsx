/**
 * Configurable automations — create/enable/disable/run rules (Phase 7).
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
  actions?: { type?: string }[];
};

export function AutomationsScreen() {
  const navigate = useNavigate();
  const { tenantId } = useTenant();
  const [rules, setRules] = useState<Rule[]>([]);
  const [log, setLog] = useState<unknown[]>([]);
  const [name, setName] = useState("Fee overdue reminder");
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
    try {
      await apiRequest(tenantPath(tenantId, "/automations/rules"), {
        method: "POST",
        body: {
          name: name.trim(),
          enabled: true,
          trigger: { type: "manual" },
          conditions: [],
          actions: [{ type: "fee_reminder", params: {} }],
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
    setMsg(`Ran: ${JSON.stringify(res).slice(0, 120)}`);
    await load();
  }

  const nav = buildDeskNav(navigate, "settings");

  return (
    <AppShell brand="CohortOS" navItems={nav} crumb="Automations">
      <div className="view" data-testid="automations">
        <h1 className="view-title">Automations</h1>
        <p className="caption muted">
          Triggers, conditions, and actions — enable or disable without changing code.
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
          <p className="caption muted">Default action: fee reminder (manual trigger).</p>
          <Button variant="primary" onClick={() => void createRule()}>
            Save automation
          </Button>
        </Card>
        <div style={{ marginTop: 16, display: "grid", gap: 12 }}>
          {rules.map((r) => (
            <Card key={r.id} title={r.name || r.id}>
              <p className="caption muted">
                Trigger: {r.trigger?.type || "manual"} · Actions:{" "}
                {(r.actions || []).map((a) => a.type).join(", ") || "—"} ·{" "}
                {r.enabled === false ? "Disabled" : "Enabled"}
              </p>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <Button size="sm" variant="outline" onClick={() => void run(r)}>
                  Run now
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => void toggle(r, r.enabled === false)}
                >
                  {r.enabled === false ? "Enable" : "Disable"}
                </Button>
              </div>
            </Card>
          ))}
        </div>
        <Card title="Action log" style={{ marginTop: 16 }}>
          {log.length === 0 ? (
            <p className="caption muted">No runs yet.</p>
          ) : (
            <pre className="caption" style={{ whiteSpace: "pre-wrap", maxHeight: 240, overflow: "auto" }}>
              {JSON.stringify(log.slice().reverse(), null, 2)}
            </pre>
          )}
        </Card>
      </div>
    </AppShell>
  );
}
