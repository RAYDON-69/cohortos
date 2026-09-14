import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { buildDeskNav } from "../../nav/deskNav";
import { AppShell } from "../../shell/AppShell";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { DataTable } from "../../components/DataTable"
import type { Column } from "../../components/DataTable"
import { FormField, TextInput, SelectInput } from "../../components/FormField";
import { useLocale } from "../../i18n/LocaleContext";
import { listStaff, createStaff, assignStaffRole, loadTokens } from "../../api/client"
import type { StaffRow, RoleRow, ApiError } from "../../api/client"
import "../../components/Button.css";
import "../../components/Card.css";
import "../../components/DataTable.css";
import "../../components/FormField.css";
import "../../shell/AppShell.css";

/**
 * Staff / roles — Portion 18
 * Role assignment is owner-only (API rejects is_owner=false).
 */

const ROLE_OPTIONS = ["owner", "desk", "teacher", "assistant"];

export function StaffRolesScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";
  const [isOwner, setIsOwner] = useState(true);

  const [staff, setStaff] = useState<StaffRow[]>([]);
  const [roles, setRoles] = useState<RoleRow[]>([]);
  const [username, setUsername] = useState("");
  const [roleName, setRoleName] = useState("desk");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listStaff(tenantId);
      setStaff(res.staff || []);
      setRoles(res.roles || []);
    } catch (e) {
      setError((e as ApiError).detail || t("networkError"));
    } finally {
      setLoading(false);
    }
  }, [tenantId, t]);

  useEffect(() => {
    load();
  }, [load]);

  async function onCreate() {
    if (!username.trim()) return;
    if (!isOwner) {
      setError("Only the owner can add staff or change roles.");
      return;
    }
    setSaving(true);
    try {
      await createStaff(tenantId, { username: username.trim(), role_name: roleName });
      setUsername("");
      await load();
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setSaving(false);
    }
  }

  async function onAssign(userId: string, nextRole: string) {
    if (!isOwner) {
      setError("Only the owner can change staff roles.");
      return;
    }
    setSaving(true);
    try {
      await assignStaffRole(tenantId, userId, nextRole, true);
      await load();
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setSaving(false);
    }
  }

  const columns: Column<StaffRow>[] = [
    {
      key: "username",
      header: "Username",
      essential: true,
      sortable: true,
    },
    {
      key: "role_name",
      header: "Role",
      essential: true,
      render: (r) => (
        <span className="badge badge-neutral-info" role="status">
          {r.role_name || "—"}
        </span>
      ),
    },
    {
      key: "actions",
      header: "Assign role",
      essential: true,
      render: (r) => (
        <SelectInput
          value={r.role_name || "desk"}
          disabled={!isOwner}
          onChange={(e) => void onAssign(r.id, e.target.value)}
          aria-label={`Role for ${r.username}`}
        >
          {ROLE_OPTIONS.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </SelectInput>
      ),
    },
  ];

  const nav = buildDeskNav(navigate, "settings");

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb="Owner / Desk · Staff">
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
        <Button variant="outline" onClick={() => navigate("/settings/staff")}>Staff</Button>
        <Button variant="outline" onClick={() => navigate("/settings/messaging")}>Messaging</Button>
        <Button variant="outline" onClick={() => navigate("/settings/mode")}>Mode</Button>
        <Button variant="outline" onClick={() => navigate("/attendance")}>← Back to desk</Button>
      </div>
      <h2 className="view-title">Staff & roles</h2>
      <p className="caption muted" style={{ marginBottom: 16 }}>
        Role changes are owner-only and audit-logged at the data layer.
      </p>

      <label style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 16, fontSize: 13 }}>
        <input type="checkbox" checked={isOwner} onChange={(e) => setIsOwner(e.target.checked)} />
        Acting as owner (demo)
      </label>

      {error && (
        <div className="warning-banner" role="alert" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      <Card style={{ marginBottom: 24 } as React.CSSProperties}>
        <div className="eyebrow">Add staff</div>
        <FormField id="st-user" label="Username" required>
          <TextInput id="st-user" value={username} onChange={(e) => setUsername(e.target.value)} />
        </FormField>
        <FormField id="st-role" label="Role">
          <SelectInput id="st-role" value={roleName} onChange={(e) => setRoleName(e.target.value)}>
            {ROLE_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </SelectInput>
        </FormField>
        <Button
          variant="primary"
          onClick={() => void onCreate()}
          loading={saving}
          disabled={!isOwner || !username.trim()}
          disabledReason={!isOwner ? "Only owner can add staff" : undefined}
        >
          Add staff
        </Button>
      </Card>

      <DataTable
        columns={columns}
        rows={staff}
        rowKey={(r) => r.id}
        loading={loading}
        emptyTitle="No staff yet"
        emptyBody="Add the first desk or teacher account."
      />

      {!isOwner && (
        <p className="caption" style={{ marginTop: 12 }}>
          {t("notAvailableForRole")} — role assignment is owner-only.
        </p>
      )}
    </AppShell>
  );
}
