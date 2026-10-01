import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { buildDeskNav } from "../../nav/deskNav";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { useTenant } from "../../hooks/useTenant";
import { apiRequest, tenantPath, type ApiError } from "../../api/client";

type CardT = {
  id: string;
  kind: string;
  name: string;
  phone: string;
  detail?: string;
  tel_link?: string;
  whatsapp_link?: string;
  sms_link?: string;
};

export function CallDeskScreen() {
  const navigate = useNavigate();
  const { tenantId } = useTenant();
  const [cards, setCards] = useState<CardT[]>([]);
  const [script, setScript] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function load() {
    if (!tenantId) return;
    try {
      const r = await apiRequest<{ cards?: CardT[] }>(tenantPath(tenantId, "/call-desk/queue"), {
        method: "POST",
        body: {
          fee_dues: [{ name: "Demo Karim", phone: "01711112222", detail: "Fee 500 overdue" }],
          absences: [{ name: "Demo Rahim", phone: "01811112222", detail: "Absent 3 days" }],
        },
      });
      setCards(r.cards || []);
    } catch (e) {
      setError((e as ApiError)?.detail || "Queue failed");
    }
  }

  async function genScript(card: CardT) {
    if (!tenantId) return;
    const r = await apiRequest<{ script?: string }>(tenantPath(tenantId, "/call-desk/script"), {
      method: "POST",
      body: { card, language: "bn" },
    });
    setScript(r.script || "");
  }

  async function outcome(card: CardT, outcome: string) {
    if (!tenantId) return;
    const human_action_id = crypto.randomUUID();
    await apiRequest(tenantPath(tenantId, "/call-desk/outcome"), {
      method: "POST",
      body: { card_id: card.id, outcome, notes: outcome, human_action_id },
    });
    setMsg(`Logged ${outcome}`);
  }

  const nav = buildDeskNav(navigate, "settings");
  return (
    <AppShell brand="CohortOS" navItems={nav} crumb="Call desk">
      <div className="view" data-testid="call-desk">
        <h1 className="view-title">Call desk</h1>
        <p className="caption muted">Human-placed calls only — no autodial.</p>
        {error && <p className="error-text">{error}</p>}
        {msg && <p role="status">{msg}</p>}
        <Button variant="primary" onClick={() => void load()}>
          Load queue
        </Button>
        {cards.map((c) => (
          <Card key={c.id} title={`${c.kind}: ${c.name}`}>
            <p className="caption">{c.detail}</p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {c.tel_link && (
                <a href={c.tel_link}>
                  <Button variant="primary">Call</Button>
                </a>
              )}
              {c.whatsapp_link && (
                <a href={c.whatsapp_link} target="_blank" rel="noreferrer">
                  <Button variant="secondary">WhatsApp</Button>
                </a>
              )}
              <Button variant="ghost" onClick={() => void genScript(c)}>
                Script
              </Button>
              <Button variant="ghost" onClick={() => void outcome(c, "reached")}>
                Reached
              </Button>
              <Button variant="ghost" onClick={() => void outcome(c, "no_answer")}>
                No answer
              </Button>
            </div>
          </Card>
        ))}
        {script && (
          <pre data-testid="call-desk-script" style={{ whiteSpace: "pre-wrap" }}>
            {script}
          </pre>
        )}
      </div>
    </AppShell>
  );
}
