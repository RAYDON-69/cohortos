import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { buildDeskNav } from "../../nav/deskNav";
import { Card } from "../../components/Card";
import { useLocale } from "../../i18n/LocaleContext";
import { downloadDiagnostics, loadTokens } from "../../api/client";

export function SupportLegalScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const nav = buildDeskNav(navigate, "settings", {
    attendance: t("navAttendance"),
    admissions: t("navAdmissions"),
    fees: t("navFees") || "Fees",
  });
  const [diagBusy, setDiagBusy] = useState(false);
  const [diagMsg, setDiagMsg] = useState<string | null>(null);

  async function onDownloadDiagnostics() {
    setDiagBusy(true);
    setDiagMsg(null);
    try {
      const tokens = loadTokens() as { tenant_id?: string };
      const tenantId = tokens.tenant_id || "";
      if (!tenantId) {
        setDiagMsg("No centre selected — sign in again.");
        return;
      }
      const blob = await downloadDiagnostics(tenantId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cohortos-diagnostics-${tenantId.slice(0, 8)}.zip`;
      a.click();
      URL.revokeObjectURL(url);
      setDiagMsg("Diagnostics downloaded (PII redacted).");
    } catch (e) {
      setDiagMsg(e instanceof Error ? e.message : "Download failed");
    } finally {
      setDiagBusy(false);
    }
  }

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb="Support">
      <h2 className="view-title">Support & legal</h2>
      <p className="caption muted" style={{ marginBottom: 20 }}>
        Contact, about, terms, and feedback.
      </p>
      <div style={{ display: "grid", gap: 16, maxWidth: 640 }}>
        <Card>
          <h3 className="card-title">Contact</h3>
          <p className="caption">Email: support@cohortos.app</p>
        </Card>
        <Card>
          <h3 className="card-title">About CohortOS</h3>
          <p className="caption">
            Coaching-centre desk: attendance, admissions, fees, exams, offline-first sync. Version 0.11.0.
          </p>
        </Card>
        <Card>
          <h3 className="card-title">Diagnostics</h3>
          <p className="caption muted" style={{ marginBottom: 8 }}>
            Download a PII-redacted zip (versions, config, log tail) for pilot support. Owner/admin only.
          </p>
          <button
            type="button"
            className="btn primary"
            data-testid="download-diagnostics"
            disabled={diagBusy}
            onClick={onDownloadDiagnostics}
          >
            {diagBusy ? "Preparing…" : "Download diagnostics"}
          </button>
          {diagMsg ? (
            <p className="caption" style={{ marginTop: 8 }}>
              {diagMsg}
            </p>
          ) : null}
        </Card>
        <Card>
          <h3 className="card-title">Terms of service</h3>
          <p className="caption muted">Placeholder — publish legal terms before production scale-up.</p>
        </Card>
        <Card>
          <h3 className="card-title">Feedback</h3>
          <p className="caption">Report bugs with steps to reproduce via your pilot support channel.</p>
        </Card>
        <p>
          <Link to="/settings">← All settings</Link>
        </p>
      </div>
    </AppShell>
  );
}
