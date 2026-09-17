import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { FormField, TextInput, SelectInput } from "../../components/FormField";
import { ModalConfirm } from "../../components/Confirm";
import { useLocale } from "../../i18n/LocaleContext";
import { listVault, createVaultResource, uploadVaultResource, vaultContentUrl, setVaultAccessRules, relaxVaultProtection, restoreVaultProtection, listBatches, loadTokens, ensureAccessToken } from "../../api/client"
import type { VaultResource, AccessRuleRow, BatchRow, ApiError } from "../../api/client"
import "../../components/Button.css";
import "../../components/Card.css";
import "../../components/FormField.css";
import "../../components/Confirm.css";
import "../../shell/AppShell.css";

/**
 * Vault management (owner) — Portion 17
 * Access-rule builder: AND/OR + four rule types.
 * "Protection relaxed" is a large visible label, not a small icon.
 * Desk anti-leak: "not available for your role" (not hidden).
 */

const RULE_KINDS = [
  { value: "min_attendance", label: "Min attendance %" },
  { value: "sat_last_exam", label: "Sat last exam" },
  { value: "paid_up", label: "Paid up (current month)" },
  { value: "expires_on", label: "Expires on (date)" },
];

export function VaultManagementScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";
  // Demo role switch for anti-leak visibility
  const [actorRole, setActorRole] = useState<"owner" | "desk" | "teacher">("owner");

  const [resources, setResources] = useState<VaultResource[]>([]);
  const [batches, setBatches] = useState<BatchRow[]>([]);
  const [title, setTitle] = useState("");
  const [topic, setTopic] = useState("");
  const [url, setUrl] = useState("");
  const [fileName, setFileName] = useState("");
  const [fileBase64, setFileBase64] = useState("");
  const [fileMime, setFileMime] = useState("application/octet-stream");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [operator, setOperator] = useState<"and" | "or">("and");
  const [rules, setRules] = useState<AccessRuleRow[]>([]);
  const [newKind, setNewKind] = useState("min_attendance");
  const [newValue, setNewValue] = useState("75");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [relaxConfirm, setRelaxConfirm] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [v, b] = await Promise.all([listVault(tenantId), listBatches(tenantId)]);
      setResources(v.resources || []);
      setBatches(b.batches || []);
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
    const res = resources.find((r) => r.id === selectedId);
    if (!res) return;
    const ar = res.access_rules || {};
    setOperator((ar.operator as "and" | "or") || "and");
    setRules(ar.rules || []);
  }, [selectedId, resources]);

  async function onCreate() {
    if (!title.trim()) return;
    if (actorRole === "desk") {
      setError("Not available for your role — desk cannot manage vault protection settings.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      if (fileBase64 && fileName) {
        await uploadVaultResource(tenantId, {
          title: title.trim(),
          filename: fileName,
          content_base64: fileBase64,
          content_type: fileMime,
          topic,
        });
      } else {
        await createVaultResource(tenantId, {
          title: title.trim(),
          topic,
          url,
          resource_type: url ? "link" : "pdf",
          actor_role: actorRole,
        });
      }
      setTitle("");
      setTopic("");
      setUrl("");
      setFileName("");
      setFileBase64("");
      await load();
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setSaving(false);
    }
  }

  function onPickFile(file: File | null) {
    if (!file) return;
    setFileName(file.name);
    setFileMime(file.type || "application/octet-stream");
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const b64 = result.includes(",") ? result.split(",")[1] : result;
      setFileBase64(b64);
      if (!title.trim()) setTitle(file.name);
    };
    reader.readAsDataURL(file);
  }

  async function onOpenResource(resourceId: string) {
    try {
      const token = await ensureAccessToken();
      const url = vaultContentUrl(tenantId, resourceId);
      const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const obj = URL.createObjectURL(blob);
      window.open(obj, "_blank", "noopener,noreferrer");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not open file");
    }
  }

  async function onSaveRules() {
    if (!selectedId) return;
    if (actorRole === "desk") {
      setError("Not available for your role — desk cannot edit access rules.");
      return;
    }
    setSaving(true);
    try {
      await setVaultAccessRules(tenantId, selectedId, operator, rules);
      await load();
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setSaving(false);
    }
  }

  async function onRelax() {
    if (!selectedId) return;
    setSaving(true);
    try {
      await relaxVaultProtection(tenantId, selectedId, actorRole);
      setRelaxConfirm(false);
      await load();
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setSaving(false);
    }
  }

  async function onRestore() {
    if (!selectedId) return;
    setSaving(true);
    try {
      await restoreVaultProtection(tenantId, selectedId, actorRole);
      await load();
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setSaving(false);
    }
  }

  const selected = resources.find((r) => r.id === selectedId);
  const isRelaxed = selected?.protection_level === "relaxed";
  const deskBlocked = actorRole === "desk";

  const nav = [
    { id: "exams", label: t("navExams"), onClick: () => navigate("/exams") },
    { id: "vault", label: t("navVault"), active: true },
  ];

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb="Owner / Desk · Vault">
      <h2 className="view-title">Content vault</h2>
      <p className="caption muted" style={{ marginBottom: 16 }}>
        Access rules compose with AND/OR. Protection relaxed must be impossible to miss.
      </p>

      <div style={{ marginBottom: 16 }}>
        <FormField id="role-demo" label="Acting as (demo RBAC)">
          <SelectInput
            id="role-demo"
            value={actorRole}
            onChange={(e) => setActorRole(e.target.value as typeof actorRole)}
          >
            <option value="owner">Owner</option>
            <option value="teacher">Teacher</option>
            <option value="desk">Desk</option>
          </SelectInput>
        </FormField>
        {deskBlocked && (
          <div className="warning-banner" role="status">
            Not available for your role — desk cannot set or relax anti-leak protection.
          </div>
        )}
      </div>

      {error && (
        <div className="warning-banner" role="alert" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      <section style={{ marginBottom: 28 }}>
        <div className="eyebrow">Add resource</div>
        <Card>
          <FormField id="vr-title" label="Title" required>
            <TextInput id="vr-title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </FormField>
          <FormField id="vr-topic" label="Topic">
            <TextInput id="vr-topic" value={topic} onChange={(e) => setTopic(e.target.value)} />
          </FormField>
          <FormField id="vr-file" label="Attach file">
            <input
              id="vr-file"
              type="file"
              onChange={(e) => onPickFile(e.target.files?.[0] || null)}
            />
            {fileName && <p className="caption muted">Selected: {fileName}</p>}
          </FormField>
          <FormField id="vr-url" label="Or external link (optional)">
            <TextInput id="vr-url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" />
          </FormField>
          <Button
            variant="primary"
            onClick={() => void onCreate()}
            loading={saving}
            disabled={!title.trim() || deskBlocked}
            disabledReason={deskBlocked ? t("notAvailableForRole") : undefined}
          >
            Create resource
          </Button>
        </Card>
      </section>

      <section style={{ marginBottom: 28 }}>
        <div className="eyebrow">Resources</div>
        {loading && <p className="caption muted">{t("loadingView")}</p>}
        <div className="vault-list">
          {resources.map((r) => {
            const relaxed = r.protection_level === "relaxed";
            return (
              <button
                key={r.id}
                type="button"
                className={`vault-item ${selectedId === r.id ? "selected" : ""} ${relaxed ? "is-relaxed" : ""}`}
                onClick={() => setSelectedId(r.id)}
              >
                <div className="vault-item-top">
                  <strong>{r.title}</strong>
                  <span className="caption">{r.topic || r.resource_type}</span>
                </div>
                {relaxed ? (
                  <div className="protection-relaxed-banner" role="status">
                    Protection relaxed
                  </div>
                ) : (
                  <span className="badge badge-payment-locked" role="status">
                    Owner-only protection
                  </span>
                )}
              </button>
            );
          })}
          {!loading && resources.length === 0 && (
            <p className="caption muted">No resources yet.</p>
          )}
        </div>
      </section>

      {selected && (
        <section>
          <Card variant={isRelaxed ? "queue-flagged" : "standard"}>
            {isRelaxed && (
              <div className="protection-relaxed-banner large" role="status">
                Protection relaxed
              </div>
            )}
            <h3 className="card-title">{String(selected.title ?? "")}</h3>
            <p className="caption">
              {String(selected.resource_type ?? "")} · {String(selected.topic || "—")} · level{" "}
              {String(selected.protection_level ?? "")}
            </p>
            {(Boolean(selected.file_path) || Boolean((selected as { url?: string }).url)) && (
              <p style={{ marginTop: 12 }}>
                <Button variant="primary" size="sm" onClick={() => void onOpenResource(selected.id)}>
                  Open / view file
                </Button>
              </p>
            )}

            <div className="eyebrow" style={{ marginTop: 16 }}>
              Access rules · AND/OR composition
            </div>
            <FormField id="op" label="Combine rules with">
              <SelectInput
                id="op"
                value={operator}
                onChange={(e) => setOperator(e.target.value as "and" | "or")}
                disabled={deskBlocked}
              >
                <option value="and">AND — all must pass</option>
                <option value="or">OR — any may pass</option>
              </SelectInput>
            </FormField>
            <ul className="rule-list">
              {rules.map((rule, i) => (
                <li key={i}>
                  <span className="mono-data">{rule.kind}</span>
                  {rule.value != null && rule.value !== "" && (
                    <span> = {String(rule.value)}</span>
                  )}
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={deskBlocked}
                    onClick={() => setRules((rs) => rs.filter((_, j) => j !== i))}
                  >
                    Remove
                  </Button>
                </li>
              ))}
            </ul>
            <div className="rule-add">
              <SelectInput
                value={newKind}
                onChange={(e) => setNewKind(e.target.value)}
                disabled={deskBlocked}
              >
                {RULE_KINDS.map((k) => (
                  <option key={k.value} value={k.value}>
                    {k.label}
                  </option>
                ))}
              </SelectInput>
              <TextInput
                value={newValue}
                onChange={(e) => setNewValue(e.target.value)}
                placeholder="Value"
                disabled={deskBlocked}
              />
              <Button
                size="sm"
                variant="outline"
                disabled={deskBlocked}
                disabledReason={deskBlocked ? t("notAvailableForRole") : undefined}
                onClick={() =>
                  setRules((rs) => [
                    ...rs,
                    {
                      kind: newKind,
                      value:
                        newKind === "min_attendance"
                          ? Number(newValue) || 0
                          : newValue,
                    },
                  ])
                }
              >
                Add rule
              </Button>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 16 }}>
              <Button
                variant="primary"
                onClick={() => void onSaveRules()}
                loading={saving}
                disabled={deskBlocked}
                disabledReason={deskBlocked ? t("notAvailableForRole") : undefined}
              >
                Save access rules
              </Button>
              {!isRelaxed ? (
                <Button
                  variant="outline"
                  onClick={() => setRelaxConfirm(true)}
                  disabled={deskBlocked}
                  disabledReason={deskBlocked ? t("notAvailableForRole") : undefined}
                >
                  Relax protection
                </Button>
              ) : (
                <Button
                  variant="outline"
                  onClick={() => void onRestore()}
                  disabled={deskBlocked}
                  disabledReason={deskBlocked ? t("notAvailableForRole") : undefined}
                >
                  Restore protection
                </Button>
              )}
            </div>
          </Card>
        </section>
      )}

      <ModalConfirm
        open={relaxConfirm}
        title="Relax anti-leak protection"
        consequence="Watermark, no-download, and session token requirements will be turned off for this resource. The list will show a highly visible “Protection relaxed” label. This is audit-logged."
        confirmLabel="Relax protection"
        onCancel={() => setRelaxConfirm(false)}
        onConfirm={() => void onRelax()}
        loading={saving}
        destructive
      />

      <style>{`
        .vault-list {
          display: grid;
          gap: 10px;
        }
        .vault-item {
          text-align: left;
          background: var(--white);
          border: 1px solid var(--border);
          border-radius: 12px;
          padding: 14px 16px;
          cursor: pointer;
          font-family: inherit;
          width: 100%;
        }
        .vault-item.selected {
          border-color: var(--sage-700);
          box-shadow: var(--shadow);
        }
        .vault-item.is-relaxed {
          border-color: var(--error);
          background: var(--error-bg);
        }
        .vault-item-top {
          display: flex;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 8px;
        }
        .protection-relaxed-banner {
          display: block;
          width: 100%;
          background: var(--error-bg);
          color: var(--error);
          font-weight: 700;
          font-size: 13px;
          letter-spacing: 0.04em;
          text-transform: uppercase;
          padding: 8px 12px;
          border-radius: 8px;
          margin-top: 4px;
        }
        .protection-relaxed-banner.large {
          font-size: 15px;
          padding: 12px 16px;
          margin-bottom: 12px;
        }
        .rule-list {
          list-style: none;
          margin: 0 0 12px;
          padding: 0;
        }
        .rule-list li {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 6px 0;
          border-bottom: 1px solid var(--border);
          font-size: 14px;
        }
        .rule-add {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          align-items: center;
        }
        .rule-add .form-input, .rule-add select {
          max-width: 200px;
        }
      `}</style>
    </AppShell>
  );
}
