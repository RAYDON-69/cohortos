/**
 * Settings information architecture — grouped, not one flat list.
 */
import { Link } from "react-router-dom";
import { useNavigate } from "react-router-dom";
import { AppShell } from "../../shell/AppShell";
import { buildDeskNav } from "../../nav/deskNav";
import { Card } from "../../components/Card";
import { useLocale } from "../../i18n/LocaleContext";
import "../../components/Card.css";
import "../../shell/AppShell.css";

type LinkItem = { to: string; title: string; body: string };
type Section = { heading: string; items: LinkItem[] };

const SECTIONS: Section[] = [
  {
    heading: "Account",
    items: [
      { to: "/settings/staff", title: "Staff & roles", body: "Invite staff and assign owner / desk / teacher roles." },
    ],
  },
  {
    heading: "Centre",
    items: [
      { to: "/settings/mode", title: "Centre mode", body: "Offline-first and centre operating mode." },
      { to: "/settings/biometric", title: "Biometric devices", body: "Attendance devices and student device IDs." },
      { to: "/settings/backup", title: "Backup & export", body: "Local database snapshots." },
      { to: "/settings/conflicts", title: "Sync conflicts", body: "Owner review of offline sync conflicts." },
    ],
  },
  {
    heading: "Billing / License",
    items: [
      { to: "/support", title: "License & support", body: "Plan status, lockouts, and how to contact support." },
    ],
  },
  {
    heading: "Integrations",
    items: [
      { to: "/settings/storage", title: "File storage", body: "Local or Google Drive backend for vault files." },
      { to: "/settings/messaging", title: "Messaging (SMS)", body: "Twilio and reminder preferences." },
      { to: "/settings/ai-keys", title: "AI API keys", body: "Groq, NVIDIA NIM, OpenAI, Anthropic, or Gemini developer keys." },
      { to: "/settings/automations", title: "Automations", body: "Triggers, conditions, and actions for reminders and nags." },
    ],
  },
  {
    heading: "Notifications",
    items: [
      { to: "/settings/messaging", title: "Fee & attendance alerts", body: "When parents get fee reminders and nag-list SMS." },
    ],
  },
  {
    heading: "Support / Legal",
    items: [
      { to: "/support", title: "Support, About, Terms", body: "Contact, feedback, and legal pages." },
    ],
  },
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
    <AppShell brand={t("appName")} navItems={nav} crumb="Settings">
      <h2 className="view-title">Settings</h2>
      <p className="caption muted" style={{ marginBottom: 20 }}>
        Account, centre, billing, integrations, and support — grouped so you can find things quickly.
      </p>
      {SECTIONS.map((sec) => (
        <section key={sec.heading} style={{ marginBottom: 28 }}>
          <h3 className="eyebrow" style={{ marginBottom: 10 }}>
            {sec.heading}
          </h3>
          <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}>
            {sec.items.map((l) => (
              <Link key={l.to + l.title} to={l.to} style={{ textDecoration: "none", color: "inherit" }}>
                <Card>
                  <h3 className="card-title" style={{ marginBottom: 6 }}>
                    {l.title}
                  </h3>
                  <p className="caption muted">{l.body}</p>
                </Card>
              </Link>
            ))}
          </div>
        </section>
      ))}
    </AppShell>
  );
}
