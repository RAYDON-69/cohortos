/**
 * Unified Settings entry — links scattered config screens.
 */
import { Link } from "react-router-dom";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { buildDeskNav } from "../../nav/deskNav";
import { Card } from "../../components/Card";
import { useLocale } from "../../i18n/LocaleContext";
import "../../components/Card.css";
import "../../shell/AppShell.css";

const LINKS: { to: string; title: string; body: string }[] = [
  { to: "/settings/staff", title: "Staff & roles", body: "Invite staff and assign owner / desk / teacher roles." },
  { to: "/settings/messaging", title: "Messaging", body: "SMS and reminder preferences." },
  { to: "/settings/mode", title: "Centre mode", body: "Offline-first and centre operating mode." },
  { to: "/settings/biometric", title: "Biometric devices", body: "Attendance devices and student device IDs." },
  { to: "/settings/storage", title: "File storage", body: "Local or Google Drive backend for vault files." },
  { to: "/settings/backup", title: "Backup & export", body: "Local database snapshots." },
  { to: "/settings/conflicts", title: "Sync conflicts", body: "Owner review of offline sync conflicts." },
  { to: "/support", title: "Support & legal", body: "Contact, about, terms, and feedback." },
];

export function SettingsHubScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const nav = buildDeskNav(navigate, "settings", {
    attendance: t("navAttendance"),
    admissions: t("navAdmissions"),
    fees: t("navFees") || "Fees",
  });

  return (
    <AppShell brand={t("appName")} navItems={nav} crumb="Owner / Desk · Settings">
      <h2 className="view-title">Settings</h2>
      <p className="caption muted" style={{ marginBottom: 20 }}>
        All centre configuration in one place.
      </p>
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}>
        {LINKS.map((l) => (
          <Link key={l.to} to={l.to} style={{ textDecoration: "none", color: "inherit" }}>
            <Card>
              <h3 className="card-title" style={{ marginBottom: 6 }}>
                {l.title}
              </h3>
              <p className="caption muted">{l.body}</p>
            </Card>
          </Link>
        ))}
      </div>
    </AppShell>
  );
}
