/**
 * Biometric device settings — PRD §16 / SPEC §2.
 * Add device (IP/port/label), test, pull, map device_user_id, disable → manual fallback.
 * If device library missing: plain-language banner and force manual (no crash, no "install pyzk").
 */
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { buildDeskNav } from "../../nav/deskNav";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { FormField, TextInput } from "../../components/FormField";
import { useTenant } from "../../hooks/useTenant";
import {
  getBiometricStatus,
  registerBiometricDevice,
  testBiometricDevice,
  disableBiometricDevice,
  linkDeviceUser,
  linkDeviceUserBulk,
  apiRequest,
  tenantPath,
  type BiometricDeviceRow,
  type ApiError,
} from "../../api/client";

async function safePull(tenantId: string, deviceId: string) {
  return apiRequest<{ pulled?: number; accepted?: number }>(
    tenantPath(tenantId, "/attendance/biometric/pull"),
    { method: "POST", body: { device_id: deviceId } }
  );
}

export function BiometricDevicesScreen() {
  const navigate = useNavigate();
  const { tenantId } = useTenant();
  const [devices, setDevices] = useState<BiometricDeviceRow[]>([]);
  const [libraryAvailable, setLibraryAvailable] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [ip, setIp] = useState("");
  const [port, setPort] = useState("4370");
  const [msg, setMsg] = useState<string | null>(null);
  const [linkStudent, setLinkStudent] = useState("");
  const [linkUid, setLinkUid] = useState("");
  const [csvText, setCsvText] = useState("");

  const load = useCallback(async () => {
    if (!tenantId) {
      setLoading(false);
      setError("No centre selected");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await getBiometricStatus(tenantId);
      setDevices(res.devices || []);
      // Backend may still call the field pyzk_available; accept both names.
      const avail =
        (res as { device_library_available?: boolean; pyzk_available?: boolean })
          .device_library_available ??
        (res as { pyzk_available?: boolean }).pyzk_available ??
        true;
      setLibraryAvailable(Boolean(avail));
    } catch (e) {
      setError((e as ApiError)?.detail || (e as Error)?.message || "Failed to load devices");
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onAdd() {
    if (!tenantId || !name.trim()) return;
    setMsg(null);
    try {
      await registerBiometricDevice(tenantId, {
        name: name.trim(),
        ip_address: ip.trim(),
        port: Number(port) || 4370,
      });
      setName("");
      setIp("");
      await load();
      setMsg("Device added");
    } catch (e) {
      setError((e as ApiError)?.detail || "Add failed");
    }
  }

  async function onTest(id: string) {
    if (!tenantId) return;
    setMsg(null);
    try {
      const r = await testBiometricDevice(tenantId, id);
      if (!r.ok) {
        setMsg(r.message || r.error || "Connection failed — using manual entry");
      } else {
        setMsg("Connection OK");
      }
    } catch (e) {
      setMsg((e as ApiError)?.detail || "Test failed — use manual attendance");
    }
  }

  async function onDisable(id: string) {
    if (!tenantId) return;
    await disableBiometricDevice(tenantId, id);
    await load();
    setMsg("Device disabled — attendance uses manual grid only");
  }

  async function onPull(id: string) {
    if (!tenantId) return;
    if (!libraryAvailable) {
      setMsg(
        "Automatic device sync is not available on this computer yet — you can still map student IDs manually"
      );
      return;
    }
    try {
      const r = await safePull(tenantId, id);
      setMsg(`Pulled ${r.pulled ?? 0}, accepted ${r.accepted ?? 0}`);
    } catch (e) {
      setMsg((e as ApiError)?.detail || "Pull failed — use manual entry");
    }
  }

  async function onLink() {
    if (!tenantId || !linkStudent || !linkUid) return;
    await linkDeviceUser(tenantId, linkStudent, linkUid);
    setMsg("Mapped student ↔ device user id");
    setLinkUid("");
  }

  async function onBulk() {
    if (!tenantId || !csvText.trim()) return;
    const rows = csvText
      .trim()
      .split("\n")
      .map((line) => {
        const [a, b] = line.split(/[,\t]/).map((s) => s.trim());
        if (!a || !b) return null;
        if (a.includes("-") || a.length > 20) return { student_id: a, device_user_id: b };
        return { roll: a, device_user_id: b };
      })
      .filter(Boolean) as { student_id?: string; roll?: string; device_user_id: string }[];
    const r = await linkDeviceUserBulk(tenantId, rows);
    setMsg(`Bulk linked ${r.linked}; errors ${r.errors?.length ?? 0}`);
  }

  const nav = buildDeskNav(navigate, "biometric");

  return (
    <AppShell brand="CohortOS" navItems={nav} crumb="Biometric devices">
      <div className="view" data-testid="biometric-devices">
        <h1 className="view-title">Biometric devices</h1>
        <p className="caption muted">
          Connect a fingerprint / face device on your network (static IP). Device marks are preferred;
          the manual grid fills gaps when the device is offline.
        </p>

        {!libraryAvailable && (
          <div className="warning-banner" role="status" data-testid="device-library-missing">
            <p>
              <strong>Automatic device sync is not available on this computer yet.</strong>
            </p>
            <p>
              You can still map each student to a device user id below, and mark attendance manually.
              When this desk machine has the device driver installed, pull and test will work here.
            </p>
          </div>
        )}

        {msg && (
          <p className="caption" role="status" data-testid="bio-msg">
            {msg}
          </p>
        )}
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}

        {loading ? (
          <p className="caption muted">Loading devices…</p>
        ) : devices.length === 0 ? (
          <EmptyState
            title="No devices yet"
            body="Add your device IP and port below. If you do not have a device, use the manual attendance grid."
          />
        ) : (
          <div className="stack-gap">
            {devices.map((d) => (
              <Card key={d.id} title={d.name || d.id}>
                <p className="caption muted">
                  {d.ip_address}:{d.port}
                  {d.is_active === false ? " · disabled" : ""}
                </p>
                <div className="row-actions" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <Button size="sm" variant="outline" onClick={() => void onTest(d.id)}>
                    Test connection
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!libraryAvailable || d.is_active === false}
                    onClick={() => void onPull(d.id)}
                  >
                    Pull now
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => void onDisable(d.id)}>
                    Disable
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        )}

        <Card title="Add device" style={{ marginTop: 24 }}>
          <ol className="caption muted" style={{ paddingLeft: 18, marginBottom: 12 }}>
            <li>Write a short label (e.g. Front door).</li>
            <li>Enter the device static IP and port (default 4370).</li>
            <li>Add device, then Test connection.</li>
            <li>Map each student to their device user id (or import a CSV).</li>
          </ol>
          <FormField id="bio-name" label="Label" required>
            <TextInput id="bio-name" value={name} onChange={(e) => setName(e.target.value)} />
          </FormField>
          <FormField id="bio-ip" label="Static IP" hint="Example 192.168.1.201">
            <TextInput
              id="bio-ip"
              value={ip}
              onChange={(e) => setIp(e.target.value)}
              placeholder="192.168.1.201"
            />
          </FormField>
          <FormField id="bio-port" label="Port">
            <TextInput id="bio-port" value={port} onChange={(e) => setPort(e.target.value)} />
          </FormField>
          <Button variant="primary" onClick={() => void onAdd()} disabled={!name.trim()}>
            Add device
          </Button>
        </Card>

        <Card title="Map student to device user id" style={{ marginTop: 16 }}>
          <FormField id="link-stu" label="Student id">
            <TextInput
              id="link-stu"
              value={linkStudent}
              onChange={(e) => setLinkStudent(e.target.value)}
            />
          </FormField>
          <FormField id="link-uid" label="Device user id">
            <TextInput id="link-uid" value={linkUid} onChange={(e) => setLinkUid(e.target.value)} />
          </FormField>
          <Button variant="outline" onClick={() => void onLink()}>
            Save mapping
          </Button>
          <FormField
            id="bulk-csv"
            label="Bulk CSV"
            hint="student_id_or_roll,device_user_id — one per line"
          >
            <textarea
              id="bulk-csv"
              className="form-input"
              rows={4}
              value={csvText}
              onChange={(e) => setCsvText(e.target.value)}
            />
          </FormField>
          <Button variant="outline" onClick={() => void onBulk()}>
            Import mappings
          </Button>
        </Card>
      </div>
    </AppShell>
  );
}
