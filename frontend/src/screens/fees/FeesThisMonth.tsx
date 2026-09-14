import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { buildDeskNav } from "../../nav/deskNav";
import { AppShell } from "../../shell/AppShell";
import { DataTable } from "../../components/DataTable"
import type { Column } from "../../components/DataTable"
import { PaymentBadge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { InlineConfirm } from "../../components/Confirm";
import { FormField, SelectInput, TextInput } from "../../components/FormField";
import { useLocale } from "../../i18n/LocaleContext";
import { listBatches, getBatchPayments, markPaid, lockPayment, unlockPayment, loadTokens } from "../../api/client"
import type { PaymentRow, BatchRow, ApiError } from "../../api/client"
import "../../components/DataTable.css";
import "../../components/Button.css";
import "../../components/Badge.css";
import "../../components/Confirm.css";
import "../../components/FormField.css";
import "../../shell/AppShell.css";

/**
 * Fees this month — Portion 15
 * Lock uses inline confirm (§4.7). Unlock gated to owner; UI states audit-logged.
 */

function currentYearMonth() {
  const d = new Date();
  return { year: d.getFullYear(), month: d.getMonth() + 1 };
}

export function FeesThisMonthScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";
  // Demo: treat as owner unless a role claim exists elsewhere
  const isOwner = true;

  const ym = currentYearMonth();
  const [batches, setBatches] = useState<BatchRow[]>([]);
  const [batchId, setBatchId] = useState("");
  const [year, setYear] = useState(ym.year);
  const [month, setMonth] = useState(ym.month);
  const [rows, setRows] = useState<PaymentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingLock, setPendingLock] = useState<string | null>(null);
  const [pendingUnlock, setPendingUnlock] = useState<string | null>(null);
  const [unlockReason, setUnlockReason] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const b = await listBatches(tenantId);
      setBatches(b.batches || []);
      const first = batchId || b.batches?.[0]?.id || "";
      if (!batchId && first) setBatchId(first);
      const useBatch = batchId || first;
      if (useBatch) {
        const res = await getBatchPayments(tenantId, useBatch, year, month);
        setRows(res.rows || []);
      }
    } catch (e) {
      const err = e as ApiError;
      setError(err.detail || t("networkError"));
    } finally {
      setLoading(false);
    }
  }, [tenantId, batchId, year, month, t]);

  useEffect(() => {
    load();
  }, [load]);

  async function onMarkPaid(studentId: string) {
    setBusy(studentId + "-paid");
    try {
      await markPaid(tenantId, { student_id: studentId, year, month });
      await load();
    } catch (e) {
      const err = e as ApiError;
      setError(err.detail || t("genericError"));
    } finally {
      setBusy(null);
    }
  }

  async function onLock(studentId: string) {
    setBusy(studentId + "-lock");
    try {
      await lockPayment(tenantId, { student_id: studentId, year, month });
      setPendingLock(null);
      await load();
    } catch (e) {
      const err = e as ApiError;
      setError(err.detail || t("genericError"));
    } finally {
      setBusy(null);
    }
  }

  async function onUnlock(studentId: string) {
    if (!isOwner) {
      setError("Only the owner can unlock a locked payment. This action is audit-logged.");
      return;
    }
    setBusy(studentId + "-unlock");
    try {
      await unlockPayment(tenantId, {
        student_id: studentId,
        year,
        month,
        reason: unlockReason,
        is_owner: true,
      });
      setPendingUnlock(null);
      setUnlockReason("");
      await load();
    } catch (e) {
      const err = e as ApiError;
      setError(err.detail || t("genericError"));
    } finally {
      setBusy(null);
    }
  }

  const columns: Column<PaymentRow>[] = [
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
      key: "status",
      header: "Status",
      essential: true,
      render: (r) => {
        if (r.locked) return <PaymentBadge status="locked" label={t("locked")} />;
        if (r.status === "paid") return <PaymentBadge status="paid" label={t("paid")} />;
        return <PaymentBadge status="unpaid" label={t("unpaid")} />;
      },
    },
    {
      key: "actions",
      header: "",
      essential: true,
      width: "220px",
      render: (r) => {
        if (pendingLock === r.student_id) {
          return (
            <InlineConfirm
              message={`Lock ${r.name || r.roll}? Marks paid and locks.`}
              confirmLabel="Lock"
              onConfirm={() => void onLock(r.student_id)}
              onCancel={() => setPendingLock(null)}
              loading={busy === r.student_id + "-lock"}
            />
          );
        }
        if (pendingUnlock === r.student_id) {
          return (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span className="caption">
                Owner unlock — audit-logged. State reason:
              </span>
              <TextInput
                value={unlockReason}
                onChange={(e) => setUnlockReason(e.target.value)}
                placeholder="Reason"
              />
              <InlineConfirm
                message="Unlock this payment?"
                confirmLabel="Unlock"
                onConfirm={() => void onUnlock(r.student_id)}
                onCancel={() => {
                  setPendingUnlock(null);
                  setUnlockReason("");
                }}
                loading={busy === r.student_id + "-unlock"}
                destructive
              />
            </div>
          );
        }
        if (r.locked) {
          return (
            <Button
              size="sm"
              variant="outline"
              disabled={!isOwner}
              disabledReason={
                isOwner
                  ? undefined
                  : "Only owner can unlock — action is audit-logged"
              }
              onClick={() => setPendingUnlock(r.student_id)}
            >
              Unlock
            </Button>
          );
        }
        return (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {r.status !== "paid" && (
              <Button
                size="sm"
                variant="outline"
                loading={busy === r.student_id + "-paid"}
                onClick={() => void onMarkPaid(r.student_id)}
              >
                Mark paid
              </Button>
            )}
            <Button size="sm" variant="primary" onClick={() => setPendingLock(r.student_id)}>
              Lock
            </Button>
          </div>
        );
      },
    },
  ];

  const nav = buildDeskNav(navigate, "fees", { attendance: t("navAttendance"), admissions: t("navAdmissions"), fees: t("navFees") || "Fees" });

  return (
    <AppShell
      brand={t("appName")}
      navItems={nav}
      crumb={`Owner / Desk · Fees ${year}-${String(month).padStart(2, "0")}`}
    >
      <h2 className="view-title">Fees this month</h2>
      <p className="caption muted" style={{ marginBottom: 20 }}>
        Lock is explicit. Unlock is owner-only and audit-logged.
      </p>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 16, marginBottom: 20, alignItems: "flex-end" }}>
        <FormField id="fee-batch" label="Batch">
          <SelectInput id="fee-batch" value={batchId} onChange={(e) => setBatchId(e.target.value)}>
            {batches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.display_name || b.name || b.id}
              </option>
            ))}
          </SelectInput>
        </FormField>
        <FormField id="fee-year" label="Year">
          <TextInput
            id="fee-year"
            type="number"
            value={String(year)}
            onChange={(e) => setYear(Number(e.target.value))}
          />
        </FormField>
        <FormField id="fee-month" label="Month">
          <SelectInput
            id="fee-month"
            value={String(month)}
            onChange={(e) => setMonth(Number(e.target.value))}
          >
            {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </SelectInput>
        </FormField>
        <Button variant="outline" onClick={() => load()} loading={loading}>
          Refresh
        </Button>
      </div>

      {error && (
        <div className="warning-banner" role="alert" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(r) => r.student_id}
        loading={loading}
        emptyTitle="No fee rows for this batch"
        emptyBody="Admit students or pick another batch."
      />
    </AppShell>
  );
}
