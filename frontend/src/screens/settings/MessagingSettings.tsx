import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { buildDeskNav } from "../../nav/deskNav";
import { AppShell } from "../../shell/AppShell";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { FormField, TextInput } from "../../components/FormField";
import { useLocale } from "../../i18n/LocaleContext";
import { getMessagingSettings, putMessagingSettings, loadTokens } from "../../api/client"
import type { ApiError } from "../../api/client"
import "../../components/Button.css";
import "../../components/Card.css";
import "../../components/FormField.css";
import "../../shell/AppShell.css";

/**
 * Messaging settings — Portion 18
 * Channel picker + cost-cap + template editor.
 * Templates persist exactly as typed (no reformat of Bangla/Banglish).
 */

const CHANNELS = ["sms", "whatsapp", "push", "email"] as const;

export function MessagingSettingsScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";

  const [channels, setChannels] = useState<Record<string, boolean>>({
    sms: true,
    whatsapp: true,
    push: false,
    email: false,
  });
  const [costCap, setCostCap] = useState("");
  const [templates, setTemplates] = useState<Record<string, string>>({
    absence: "",
    late: "",
    payment_reminder: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getMessagingSettings(tenantId);
      if (res.channels) setChannels({ ...channels, ...res.channels });
      if (res.cost_cap != null) setCostCap(String(res.cost_cap));
      if (res.templates) setTemplates({ ...templates, ...res.templates });
    } catch (e) {
      setError((e as ApiError).detail || t("networkError"));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, t]);

  useEffect(() => {
    load();
  }, [load]);

  async function onSave() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await putMessagingSettings(tenantId, {
        channels,
        cost_cap: costCap === "" ? undefined : Number(costCap),
        templates, // exact body text, no trim/reformat of content
      });
      setSaved(true);
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setSaving(false);
    }
  }

  const nav = buildDeskNav(navigate, "settings");

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb="Owner / Desk · Messaging">
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
        <Button variant="outline" onClick={() => navigate("/settings/staff")}>Staff</Button>
        <Button variant="outline" onClick={() => navigate("/settings/messaging")}>Messaging</Button>
        <Button variant="outline" onClick={() => navigate("/settings/mode")}>Mode</Button>
        <Button variant="outline" onClick={() => navigate("/attendance")}>← Back to desk</Button>
      </div>
      <h2 className="view-title">Messaging settings</h2>
      <p className="caption muted" style={{ marginBottom: 20 }}>
        Channel picker, monthly cost cap, and message templates. Template text is stored exactly as
        typed — including Bangla and Banglish.
      </p>

      {error && (
        <div className="warning-banner" role="alert">
          {error}
        </div>
      )}
      {saved && (
        <span className="badge badge-neutral-info" role="status">
          Saved
        </span>
      )}

      {loading ? (
        <p className="caption muted">{t("loadingView")}</p>
      ) : (
        <>
          <Card>
            <div className="eyebrow">Channels</div>
            <div className="channel-grid">
              {CHANNELS.map((ch) => (
                <label key={ch} className="channel-row">
                  <input
                    type="checkbox"
                    checked={!!channels[ch]}
                    onChange={(e) =>
                      setChannels((prev) => ({ ...prev, [ch]: e.target.checked }))
                    }
                  />
                  <span>{ch}</span>
                </label>
              ))}
            </div>
            <FormField
              id="cost-cap"
              label="Monthly cost cap (৳)"
              hint="Optional soft cap for SMS/WhatsApp spend awareness"
            >
              <TextInput
                id="cost-cap"
                type="number"
                value={costCap}
                onChange={(e) => setCostCap(e.target.value)}
              />
            </FormField>
          </Card>

          <Card style={{ marginTop: 20 } as React.CSSProperties}>
            <div className="eyebrow">Templates (exact text)</div>
            {Object.keys(templates).map((name) => (
              <FormField key={name} id={`tpl-${name}`} label={name}>
                <textarea
                  id={`tpl-${name}`}
                  className="form-input template-area"
                  rows={4}
                  value={templates[name] || ""}
                  onChange={(e) =>
                    setTemplates((prev) => ({ ...prev, [name]: e.target.value }))
                  }
                  spellCheck={false}
                />
              </FormField>
            ))}
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                setTemplates((prev) => ({
                  ...prev,
                  [`custom_${Object.keys(prev).length + 1}`]: "",
                }))
              }
            >
              Add template key
            </Button>
          </Card>

          <div style={{ marginTop: 20 }}>
            <Button variant="primary" onClick={() => void onSave()} loading={saving}>
              Save messaging settings
            </Button>
          </div>
        </>
      )}

      <style>{`
        .channel-grid {
          display: flex;
          flex-wrap: wrap;
          gap: 16px;
          margin-bottom: 16px;
        }
        .channel-row {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 14px;
          text-transform: capitalize;
        }
        .template-area {
          font-family: var(--body);
          resize: vertical;
          min-height: 88px;
          line-height: 1.5;
        }
      `}</style>
    </AppShell>
  );
}
