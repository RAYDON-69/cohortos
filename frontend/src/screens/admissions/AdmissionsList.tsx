import { StudentImportPanel } from "./StudentImport";
import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { buildDeskNav } from "../../nav/deskNav";
import { AppShell } from "../../shell/AppShell";
import { DataTable } from "../../components/DataTable"
import type { Column } from "../../components/DataTable"
import { Button } from "../../components/Button";
import { FormField, TextInput, SelectInput, WarningBanner } from "../../components/FormField";
import { Card } from "../../components/Card";
import { ModalConfirm } from "../../components/Confirm";
import { useLocale } from "../../i18n/LocaleContext";
import { listStudentsApi, listBatches, listTemplates, checkDuplicates, previewRoll, admitStudent, migrateStudent, loadTokens } from "../../api/client"
import type { StudentRow, BatchRow, TemplateRow, DuplicateMatch, MigrationResult, ApiError } from "../../api/client"

/**
 * Admissions list & add + migrate — Portion 13
 * Duplicate banner above form (§4.6), migration lists history tables, atomic success/fail,
 * template AI prompt gated.
 */

export function AdmissionsListScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";

  const [students, setStudents] = useState<StudentRow[]>([]);
  const [batches, setBatches] = useState<BatchRow[]>([]);
  const [templates, setTemplates] = useState<TemplateRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Admit form
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [batchId, setBatchId] = useState("");
  const [rollPreview, setRollPreview] = useState("");
  const [dupes, setDupes] = useState<DuplicateMatch[]>([]);
  const [force, setForce] = useState(false);
  const [saving, setSaving] = useState(false);
  const [templateId, setTemplateId] = useState("");

  // Migrate
  const [migrateStudentId, setMigrateStudentId] = useState<string | null>(null);
  const [newBatchId, setNewBatchId] = useState("");
  const [migrationResult, setMigrationResult] = useState<MigrationResult | null>(null);
  const [migrating, setMigrating] = useState(false);
  const [showMigrateConfirm, setShowMigrateConfirm] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, b, tmpl] = await Promise.all([
        listStudentsApi(tenantId),
        listBatches(tenantId),
        listTemplates(tenantId),
      ]);
      setStudents(s.students || []);
      setBatches(b.batches || []);
      setTemplates(tmpl.templates || []);
      if (!batchId && b.batches?.[0]?.id) setBatchId(b.batches[0].id);
    } catch (e) {
      const err = e as ApiError;
      setError(err.detail || t("networkError"));
    } finally {
      setLoading(false);
    }
  }, [tenantId, batchId, t]);

  useEffect(() => {
    load();
  }, [load]);

  // Refetch batches when user returns to this tab or another screen created a batch
  useEffect(() => {
    const onFocus = () => {
      void load();
    };
    const onBatches = () => {
      void load();
    };
    window.addEventListener("focus", onFocus);
    window.addEventListener("cohortos:batches-changed", onBatches as EventListener);
    return () => {
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("cohortos:batches-changed", onBatches as EventListener);
    };
  }, [load]);

  useEffect(() => {
    if (!batchId) return;
    previewRoll(tenantId, batchId)
      .then((r) => setRollPreview(r.roll))
      .catch(() => setRollPreview(""));
  }, [tenantId, batchId]);

  async function onCheckDupes() {
    if (!name.trim()) return;
    try {
      const res = await checkDuplicates(tenantId, {
        name: name.trim(),
        student_phone: phone,
      });
      setDupes(res.matches || []);
      setForce(false);
    } catch (e) {
      const err = e as ApiError;
      setError(err.detail || t("genericError"));
    }
  }

  async function onAdmit() {
    setSaving(true);
    setError(null);
    try {
      await onCheckDupes();
      const res = await admitStudent(tenantId, {
        name: name.trim(),
        batch_id: batchId,
        student_phone: phone,
        force,
      });
      if ("matches" in res && (res as any).matches) {
        setDupes((res as any).matches);
        setError("Duplicate student detected — review and force only if intentional.");
        return;
      }
      setName("");
      setPhone("");
      setDupes([]);
      setForce(false);
      await load();
    } catch (e) {
      const err = e as ApiError;
      if (err.status === 409) {
        // body may have matches — client throws detail only; re-check
        await onCheckDupes();
      }
      setError(err.detail || t("genericError"));
    } finally {
      setSaving(false);
    }
  }

  async function onMigrate() {
    if (!migrateStudentId) return;
    setMigrating(true);
    setError(null);
    setMigrationResult(null);
    try {
      const res = await migrateStudent(tenantId, migrateStudentId, {
        new_batch_id: newBatchId || undefined,
      });
      setMigrationResult(res.migration);
      setShowMigrateConfirm(false);
      await load();
    } catch (e) {
      const err = e as ApiError;
      setError(err.detail || t("genericError"));
      setMigrationResult(null);
    } finally {
      setMigrating(false);
    }
  }

  const columns: Column<StudentRow>[] = [
    {
      key: "roll",
      header: "Roll",
      sortable: true,
      essential: true,
      width: "110px",
      render: (r) => <span className="mono-data">{r.roll || "—"}</span>,
    },
    { key: "name", header: "Name", sortable: true, essential: true },
    {
      key: "student_phone",
      header: "Phone",
      essential: false,
      render: (r) => <span className="mono-data">{r.student_phone || "—"}</span>,
    },
    {
      key: "batch_id",
      header: "Batch",
      essential: true,
      render: (r) => {
        const b = batches.find((x) => x.id === r.batch_id);
        return b?.display_name || b?.name || r.batch_id || "—";
      },
    },
    {
      key: "actions",
      header: "",
      essential: true,
      width: "120px",
      render: (r) => (
        <Button
          size="sm"
          variant="outline"
          onClick={(e) => {
            e.stopPropagation();
            setMigrateStudentId(r.id);
            setNewBatchId(r.batch_id || "");
            setMigrationResult(null);
            setShowMigrateConfirm(true);
          }}
        >
          Migrate
        </Button>
      ),
    },
  ];

  const studentForMigrate = students.find((s) => s.id === migrateStudentId);

  const nav = buildDeskNav(navigate, "admissions", {
    attendance: t("navAttendance"),
    admissions: t("navAdmissions"),
    fees: t("navFees") || "Fees",
  });

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb={`Owner / Desk · ${t("navAdmissions")}`}>
      <h2 className="view-title">{t("navAdmissions")}</h2>

      {error && (
        <WarningBanner>
          {error}
        </WarningBanner>
      )}

      <section style={{ marginBottom: 32 }}>
        <div className="eyebrow">Admit student</div>
        <Card className="admit-form-card">
          {dupes.length > 0 && (
            <WarningBanner>
              {dupes.map((d) => (
                <div key={d.student_id}>{d.reason}</div>
              ))}
              <div style={{ marginTop: 8, fontWeight: 500 }}>
                Resolve the conflict, or proceed only if this is intentional.
              </div>
              <label style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "center" }}>
                <input
                  type="checkbox"
                  checked={force}
                  onChange={(e) => setForce(e.target.checked)}
                />
                Force admit (idempotent)
              </label>
            </WarningBanner>
          )}

          <FormField id="adm-name" label="Name" required>
            <TextInput
              id="adm-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onBlur={() => void onCheckDupes()}
            />
          </FormField>
          <FormField id="adm-phone" label="Student phone">
            <TextInput
              id="adm-phone"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              onBlur={() => void onCheckDupes()}
              placeholder="01XXXXXXXXX"
            />
          </FormField>
          <FormField id="adm-batch" label="Batch" required>
            <SelectInput id="adm-batch" value={batchId} onChange={(e) => setBatchId(e.target.value)}>
              {batches.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.display_name || b.name || b.id}
                </option>
              ))}
            </SelectInput>
          </FormField>
          <FormField id="adm-roll" label="Roll (preview)" hint="Auto-generated from batch days + hour + next serial">
            <TextInput id="adm-roll" value={rollPreview} readOnly className="mono-data" />
          </FormField>
          <FormField
            id="adm-tmpl"
            label="Batch template"
            hint="AI system prompts are gated — request the CohortOS team to edit."
          >
            <SelectInput
              id="adm-tmpl"
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
            >
              <option value="">None</option>
              {templates.map((tmpl) => (
                <option key={tmpl.id} value={tmpl.id}>
                  {tmpl.name || tmpl.coaching_type || tmpl.id}
                </option>
              ))}
            </SelectInput>
          </FormField>
          {templateId && (
            <div className="caption muted" style={{ marginBottom: 12 }}>
              Template AI system prompt: request the CohortOS team to edit (not editable here).
            </div>
          )}
          <div style={{ display: "flex", gap: 12 }}>
            <Button variant="primary" onClick={() => void onAdmit()} loading={saving} disabled={!name.trim() || !batchId}>
              Admit
            </Button>
            <Button variant="ghost" onClick={() => void onCheckDupes()}>
              Check duplicates
            </Button>
          </div>
        </Card>
      </section>

      {migrationResult && (
        <section style={{ marginBottom: 24 }}>
          <Card variant={migrationResult.status === "completed" ? "featured" : "queue-flagged"}>
            <div className="eyebrow">Migration {migrationResult.status}</div>
            <p>
              Roll {migrationResult.old_roll} → {migrationResult.new_roll}
            </p>
            <p className="caption">
              Tables moved: {(migrationResult.tables_migrated || []).join(", ") || "none"} ·{" "}
              {migrationResult.records_moved} records
            </p>
            {migrationResult.error_message && (
              <p className="form-error">{migrationResult.error_message}</p>
            )}
          </Card>
        </section>
      )}

      <section>
        <div className="eyebrow">Students</div>
        <DataTable
          columns={columns}
          rows={students}
          rowKey={(r) => r.id}
          loading={loading}
          emptyTitle="No students yet"
          emptyBody="Admit the first student to open this list."
        />
      </section>

      <ModalConfirm
        open={showMigrateConfirm}
        title="Migrate roll / batch"
        consequence={
          studentForMigrate
            ? `This moves ${studentForMigrate.name}'s full history with them: attendance, payments, results, and threads. The change is atomic — either everything moves or nothing does.`
            : "This moves the student's full history (attendance, payments, results, threads). Atomic — all or nothing."
        }
        confirmLabel="Migrate"
        onCancel={() => setShowMigrateConfirm(false)}
        onConfirm={() => void onMigrate()}
        loading={migrating}
        destructive={false}
      />

      {showMigrateConfirm && (
        <div style={{ position: "fixed", bottom: 24, right: 24, zIndex: 1001, maxWidth: 320 }}>
          <Card>
            <FormField id="mig-batch" label="New batch">
              <SelectInput
                id="mig-batch"
                value={newBatchId}
                onChange={(e) => setNewBatchId(e.target.value)}
              >
                {batches.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.display_name || b.name || b.id}
                  </option>
                ))}
              </SelectInput>
            </FormField>
          </Card>
        </div>
      )}
            <StudentImportPanel />
</AppShell>
  );
}
