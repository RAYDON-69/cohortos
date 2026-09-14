import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { FormField, TextInput, SelectInput } from "../../components/FormField";
import { useLocale } from "../../i18n/LocaleContext";
import { founderProvision } from "../../api/client"
import type { ApiError } from "../../api/client"
import "../../components/Button.css";
import "../../components/Card.css";
import "../../components/FormField.css";
import "../../shell/AppShell.css";

/**
 * Provisioning flow — Portion 23
 */

export function ProvisionScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [mode, setMode] = useState("offline-first");
  const [tier, setTier] = useState("");
  const [students, setStudents] = useState("0");
  const [trialDays, setTrialDays] = useState("14");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);

  async function onSubmit() {
    if (!name.trim() || !code.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const res = await founderProvision({
        name: name.trim(),
        code: code.trim().toUpperCase(),
        owner_email: email,
        owner_phone: phone,
        mode,
        tier: tier || undefined,
        student_count: Number(students) || 0,
        trial_days: Number(trialDays) || 14,
      });
      setCreatedId(res.tenant.id);
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setSaving(false);
    }
  }

  const nav = [
    { id: "dash", label: "Dashboard", onClick: () => navigate("/founder") },
    { id: "provision", label: "Provision", active: true },
    { id: "pricing", label: "Pricing", onClick: () => navigate("/founder/pricing") },
  ];

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb="Founder · Provision">
      <h2 className="view-title">Provision centre</h2>
      <p className="caption muted" style={{ marginBottom: 16 }}>
        Creates a SaaS tenant in trial status. Tier is recommended from student count if left
        blank.
      </p>

      {error && (
        <div className="warning-banner" role="alert">
          {error}
        </div>
      )}

      {createdId ? (
        <Card variant="featured">
          <div className="eyebrow">Provisioned</div>
          <p>
            Centre <strong>{name}</strong> ({code.toUpperCase()}) is ready.
          </p>
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <Button variant="primary" onClick={() => navigate(`/founder/tenants/${createdId}`)}>
              Open tenant
            </Button>
            <Button variant="outline" onClick={() => navigate("/founder")}>
              Dashboard
            </Button>
          </div>
        </Card>
      ) : (
        <Card>
          <FormField id="pv-name" label="Centre name" required>
            <TextInput id="pv-name" value={name} onChange={(e) => setName(e.target.value)} />
          </FormField>
          <FormField id="pv-code" label="Code" required hint="Short unique code, e.g. DHK01">
            <TextInput
              id="pv-code"
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
            />
          </FormField>
          <FormField id="pv-email" label="Owner email">
            <TextInput id="pv-email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </FormField>
          <FormField id="pv-phone" label="Owner phone">
            <TextInput id="pv-phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </FormField>
          <FormField id="pv-mode" label="Mode">
            <SelectInput id="pv-mode" value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="offline-first">offline-first</option>
              <option value="cloud-first">cloud-first</option>
              <option value="hybrid">hybrid</option>
            </SelectInput>
          </FormField>
          <FormField id="pv-tier" label="Tier (optional)">
            <SelectInput id="pv-tier" value={tier} onChange={(e) => setTier(e.target.value)}>
              <option value="">Auto from student count</option>
              <option value="starter">starter</option>
              <option value="growth">growth</option>
              <option value="scale">scale</option>
            </SelectInput>
          </FormField>
          <FormField id="pv-n" label="Student count">
            <TextInput
              id="pv-n"
              type="number"
              value={students}
              onChange={(e) => setStudents(e.target.value)}
            />
          </FormField>
          <FormField id="pv-trial" label="Trial days">
            <TextInput
              id="pv-trial"
              type="number"
              value={trialDays}
              onChange={(e) => setTrialDays(e.target.value)}
            />
          </FormField>
          <Button
            variant="primary"
            onClick={() => void onSubmit()}
            loading={saving}
            disabled={!name.trim() || !code.trim()}
          >
            Provision
          </Button>
        </Card>
      )}
    </AppShell>
  );
}
