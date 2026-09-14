/**
 * Centre Setup Wizard — PRD Addendum §1.C
 * create centre (already done at trial) → first batch → first admission → done
 * Reachable only when tenant has zero batches. Never blocks existing centres.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { FormField, TextInput } from "../../components/FormField";
import { useTenant } from "../../hooks/useTenant";
import { useConnectivity } from "../../hooks/useConnectivity";
import {
  getSetupStatus,
  setupFirstBatch,
  admitStudent,
  listBatches,
  type ApiError,
} from "../../api/client";

type Step = "batch" | "admission" | "done";

const DAYS = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu", "Fri"];

export function CentreSetupWizardScreen() {
  const navigate = useNavigate();
  const { tenantId } = useTenant();
  const connectivity = useConnectivity();
  const offline = Boolean(
    connectivity && ("isOffline" in connectivity ? connectivity.isOffline : connectivity.state === "offline")
  );

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [needsWizard, setNeedsWizard] = useState(true);
  const [step, setStep] = useState<Step>("batch");
  const [batchId, setBatchId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [partialNote, setPartialNote] = useState<string | null>(null);

  // Batch form
  const [batchName, setBatchName] = useState("Morning batch");
  const [hour, setHour] = useState("10");
  const [days, setDays] = useState<string[]>(["Sat", "Sun"]);

  // Admission form
  const [studentName, setStudentName] = useState("");
  const [phone, setPhone] = useState("");
  const [joinCode, setJoinCode] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!tenantId) {
      setLoading(false);
      setError("No centre selected — sign in first");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const status = await getSetupStatus(tenantId);
      setNeedsWizard(status.needs_wizard);
      if (!status.needs_wizard) {
        // Existing centre — do not trap them here
        return;
      }
      if (status.steps.first_admission) {
        setStep("done");
      } else if (status.steps.first_batch) {
        setStep("admission");
      } else {
        setStep("batch");
      }
      if (status.batch_count > 0 && status.student_count === 0) {
        setPartialNote("First batch exists; add the first student to finish setup.");
        setStep("admission");
        try {
          const bl = await listBatches(tenantId);
          const first = (bl.batches || [])[0];
          if (first?.id) setBatchId(String(first.id));
        } catch {
          /* ignore */
        }
      }
    } catch (e) {
      setError((e as ApiError)?.detail || (e as Error)?.message || "Could not load setup status");
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onCreateBatch() {
    if (!tenantId || days.length === 0) return;
    setSaving(true);
    setError(null);
    try {
      const res = await setupFirstBatch(tenantId, {
        days,
        hour: Number(hour) || 10,
        name: batchName.trim() || undefined,
      });
      setBatchId(res.batch_id || (res.batch as { id?: string })?.id || null);
      setStep("admission");
      setPartialNote(null);
    } catch (e) {
      const detail = (e as ApiError)?.detail || (e as Error)?.message || "Batch create failed";
      setError(detail);
      if (String(detail).toLowerCase().includes("already has batches")) {
        setNeedsWizard(false);
      }
    } finally {
      setSaving(false);
    }
  }

  async function onAdmit() {
    if (!tenantId || !studentName.trim()) return;
    setSaving(true);
    setError(null);
    try {
      let bid = batchId;
      if (!bid) {
        const bl = await listBatches(tenantId);
        bid = (bl.batches || [])[0]?.id ? String((bl.batches || [])[0].id) : null;
        if (bid) setBatchId(bid);
      }
      if (!bid) {
        setError("Create a batch before admitting the first student.");
        setStep("batch");
        return;
      }
      const res = await admitStudent(tenantId, {
        name: studentName.trim(),
        batch_id: bid,
        student_phone: phone.trim() || undefined,
      });
      const code = (res as { join_code?: string }).join_code || null;
      setJoinCode(code);
      setStep("done");
    } catch (e) {
      setError((e as ApiError)?.detail || (e as Error)?.message || "Admission failed");
    } finally {
      setSaving(false);
    }
  }

  function toggleDay(d: string) {
    setDays((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]));
  }

  // Redirect existing centres away — never block main app routes
  if (!loading && !error && !needsWizard) {
    return <Navigate to="/attendance" replace />;
  }

  return (
    <div className="login-page" data-testid="centre-setup-wizard">
      <div className="login-card" style={{ maxWidth: 480 }}>
        <h1 className="view-title">Centre setup</h1>
        <p className="caption muted">
          First-run bootstrap — only shown when this centre has no batches yet.
        </p>

        {offline && (
          <div className="banner banner-info" role="status" data-testid="setup-offline">
            You are offline. Setup steps queue when connectivity returns; you can still prepare
            the forms.
          </div>
        )}

        {loading && (
          <div className="skeleton-block" role="status" data-testid="setup-loading">
            Checking centre…
          </div>
        )}

        {!loading && error && (
          <div className="banner banner-error" role="alert" data-testid="setup-error">
            {error}
            <Button variant="ghost" size="sm" onClick={() => void load()}>
              Retry
            </Button>
          </div>
        )}

        {!loading && !error && needsWizard && step === "batch" && (
          <div data-testid="setup-empty-batch">
            <EmptyState
              title="No batches yet"
              body="Create the first weekly batch (days + hour). Roll numbers will use this schedule."
            />
            <FormField id="wiz-batch-name" label="Batch name" required>
              <TextInput id="wiz-batch-name" value={batchName} onChange={(e) => setBatchName(e.target.value)} />
            </FormField>
            <FormField id="wiz-hour" label="Hour (0–23)" required>
              <TextInput id="wiz-hour" type="number" min={0} max={23} value={hour} onChange={(e) => setHour(e.target.value)} />
            </FormField>
            <p className="field-label">Days</p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {DAYS.map((d) => (
                <Button
                  key={d}
                  size="sm"
                  variant={days.includes(d) ? "primary" : "outline"}
                  onClick={() => toggleDay(d)}
                >
                  {d}
                </Button>
              ))}
            </div>
            <Button
              variant="primary"
              loading={saving}
              disabled={days.length === 0 || offline}
              onClick={() => void onCreateBatch()}
              style={{ marginTop: 16 }}
            >
              Create first batch
            </Button>
            <p className="caption muted" style={{ marginTop: 12 }}>
              <Link to="/attendance">Skip to desk</Link> — you can finish later from Batches.
            </p>
          </div>
        )}

        {!loading && !error && needsWizard && step === "admission" && (
          <div data-testid="setup-admission">
            {partialNote && (
              <p className="caption" data-testid="setup-partial">
                {partialNote}
              </p>
            )}
            <h2 className="card-title">First admission</h2>
            <FormField id="wiz-stu" label="Student name" required>
              <TextInput id="wiz-stu" value={studentName} onChange={(e) => setStudentName(e.target.value)} />
            </FormField>
            <FormField id="wiz-phone" label="Phone (optional)">
              <TextInput id="wiz-phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
            </FormField>
            <Button
              variant="primary"
              loading={saving}
              disabled={!studentName.trim() || offline}
              onClick={() => void onAdmit()}
            >
              Admit student
            </Button>
          </div>
        )}

        {!loading && !error && needsWizard && step === "done" && (
          <div data-testid="setup-done">
            <EmptyState
              title="Setup complete"
              body={
                joinCode
                  ? `First student admitted. Join code: ${joinCode}`
                  : "Your centre is ready for daily attendance and fees."
              }
              action={
                <Button variant="primary" onClick={() => navigate("/attendance", { replace: true })}>
                  Open attendance
                </Button>
              }
            />
          </div>
        )}
      </div>
    </div>
  );
}
