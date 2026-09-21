import { Link, useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { buildDeskNav } from "../../nav/deskNav";
import { Card } from "../../components/Card";
import { useLocale } from "../../i18n/LocaleContext";
import "../../shell/AppShell.css";

export function SupportLegalScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const nav = buildDeskNav(navigate, "settings", {
    attendance: t("navAttendance"),
    admissions: t("navAdmissions"),
    fees: t("navFees") || "Fees",
  });
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
