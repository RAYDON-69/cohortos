import React from "react";
import { SyncPill } from "../components/SyncPill";
import { OfflineBanner } from "../components/OfflineBanner";
import { useNavigate } from "react-router-dom";
import { useLocale } from "../i18n/LocaleContext";
import { GlobalSearch } from "../components/GlobalSearch";
import "./AppShell.css";

/**
 * AppShell — Owner/Desk, Teacher, Founder (§3.1)
 * Sidebar 232px + topbar. Collapses to horizontal scroll strip at ≤760px (not hamburger).
 */

export interface NavItem {
  id: string;
  label: string;
  href?: string;
  active?: boolean;
  disabled?: boolean;
  disabledReason?: string;
  onClick?: () => void;
}

export interface AppShellProps {
  brand?: string;
  navItems: NavItem[];
  crumb?: string;
  children: React.ReactNode;
  profileSlot?: React.ReactNode;
  onConflictClick?: () => void;
  /** Language toggle lives in Settings for desk personas; optional topbar slot */
  topbarExtra?: React.ReactNode;
}

export function AppShell({
  brand = "CohortOS",
  navItems,
  crumb,
  children,
  profileSlot,
  onConflictClick,
  topbarExtra,
}: AppShellProps) {
  const { t } = useLocale();
  const navigate = useNavigate();

  return (
    <div className="app-shell">
      <aside className="app-sidebar" aria-label="Main navigation">
        <button type="button" className="app-brand" style={{ background: "none", border: "none", cursor: "pointer", textAlign: "left", width: "100%" }} onClick={() => navigate("/attendance")} title="Back to desk">{brand}</button>
        <nav className="app-nav">
          {navItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`app-nav-item ${item.active ? "active" : ""} ${item.disabled ? "disabled" : ""}`}
              onClick={item.disabled ? undefined : item.onClick}
              disabled={item.disabled}
              title={item.disabled ? item.disabledReason || t("notAvailableForRole") : undefined}
              aria-current={item.active ? "page" : undefined}
            >
              <span className="app-nav-label">{item.label}</span>
              {item.disabled && (
                <span className="app-nav-locked caption">{t("notAvailableForRole")}</span>
              )}
            </button>
          ))}
        </nav>
        {profileSlot && <div className="app-profile">{profileSlot}</div>}
      </aside>

      <div className="app-main">
        <header className="app-topbar">
          <div className="app-crumb mono-data muted">{crumb || ""}</div>
          <GlobalSearch />
          <div className="app-topbar-right">
            {topbarExtra}
            <SyncPill onConflictClick={onConflictClick} />
          </div>
        </header>
        <main className="app-content">
          <OfflineBanner />
          {children}
        </main>
      </div>
    </div>
  );
}
