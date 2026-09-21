/**
 * Storage provider settings — PRD §17.
 * Configure Vault binary storage (Google Drive default / local_fs).
 * Access rules stay server-side; no raw Drive links to clients.
 */
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { buildDeskNav } from "../../nav/deskNav";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { FormField, TextInput, SelectInput } from "../../components/FormField";
import { useTenant } from "../../hooks/useTenant";
import {
  getStorageSettings,
  putStorageSettings,
  testStorageProvider,
  type ApiError,
} from "../../api/client";
import "../../components/FormField.css";
import "../../shell/AppShell.css";

export function StorageProviderScreen() {
  const navigate = useNavigate();
  const { tenantId } = useTenant();
  const [provider, setProvider] = useState("google_drive");
  const [configured, setConfigured] = useState(false);
  const [folderId, setFolderId] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [root, setRoot] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    if (!tenantId) {
      setLoading(false);
      setError("No centre selected");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await getStorageSettings(tenantId);
      setProvider(res.provider || "google_drive");
      setConfigured(Boolean(res.configured));
      setFolderId(res.folder_id || "");
    } catch (e) {
      setError((e as ApiError)?.detail || (e as Error)?.message || "Failed to load storage settings");
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onSave() {
    if (!tenantId) return;
    setSaving(true);
    setMsg(null);
    try {
      const res = await putStorageSettings(tenantId, {
        provider,
        folder_id: folderId || undefined,
        access_token: accessToken || undefined,
        root: root || undefined,
      });
      setConfigured(res.configured);
      setMsg("Storage settings saved");
      await load();
    } catch (e) {
      setError((e as ApiError)?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function onTest() {
    if (!tenantId) return;
    setMsg(null);
    try {
      const r = await testStorageProvider(tenantId);
      if (r.ok) setMsg(`Test upload OK (${r.remote_id || "ok"})`);
      else setMsg(r.message || r.error || "Test failed");
    } catch (e) {
      setMsg((e as ApiError)?.detail || "Test failed");
    }
  }

  const nav = buildDeskNav(navigate, "storage", undefined, "owner");

  return (
    <AppShell brand="CohortOS" navItems={nav} crumb="Storage">
      <div className="view" data-testid="storage-provider">
        <h1 className="view-title">Storage provider</h1>
        <p className="caption muted">
          Vault files use this backend. Protected resources never expose a raw Drive link to the
          viewer — access is checked by the API first.
        </p>

        {loading && (
          <div className="skeleton-block" role="status">
            Loading storage settings…
          </div>
        )}

        {!loading && error && (
          <div className="warning-banner" role="alert">
            {error}
            <Button variant="ghost" size="sm" onClick={() => void load()}>
              Retry
            </Button>
          </div>
        )}

        {!loading && !error && !configured && provider === "google_drive" && (
          <EmptyState
            title="Google Drive not connected"
            body="Paste an access token from your Workspace OAuth flow, or switch to local filesystem for offline centres."
          />
        )}

        {!loading && !error && (
          <Card title="Provider" eyebrow={configured ? "Configured" : "Not configured"}>
            <FormField id="stor-provider" label="Backend">
              <SelectInput
                id="stor-provider"
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
              >
                <option value="google_drive">Google Drive</option>
                <option value="local_fs">Local filesystem</option>
              </SelectInput>
            </FormField>

            {provider === "google_drive" && (
              <>
                <FormField id="stor-folder" label="Drive folder id" hint="Optional root folder">
                  <TextInput
                    id="stor-folder"
                    value={folderId}
                    onChange={(e) => setFolderId(e.target.value)}
                  />
                </FormField>
                <FormField id="stor-token" label="OAuth access token">
                  <TextInput
                    id="stor-token"
                    type="password"
                    value={accessToken}
                    onChange={(e) => setAccessToken(e.target.value)}
                    autoComplete="off"
                  />
                </FormField>
              </>
            )}

            {provider === "local_fs" && (
              <FormField id="stor-root" label="Storage root path">
                <TextInput
                  id="stor-root"
                  value={root}
                  onChange={(e) => setRoot(e.target.value)}
                  placeholder="/var/cohortos/storage"
                />
              </FormField>
            )}

            <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
              <Button variant="primary" loading={saving} onClick={() => void onSave()}>
                Save
              </Button>
              <Button variant="outline" onClick={() => void onTest()}>
                Test upload
              </Button>
            </div>
            {msg && (
              <p className="caption" role="status">
                {msg}
              </p>
            )}
          </Card>
        )}
      </div>
    </AppShell>
  );
}
