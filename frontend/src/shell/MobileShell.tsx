import React from "react";
import { SyncPill } from "../components/SyncPill";
import { OfflineBanner } from "../components/OfflineBanner";
import { useLocale } from "../i18n/LocaleContext";
import "./MobileShell.css";

/**
 * MobileShell — Student/Parent (§3.2)
 * Bottom tab bar (≤4 items). Slim header with centre name + language + sync pill.
 */

export interface TabItem {
  id: string;
  label: string;
  active?: boolean;
  onClick?: () => void;
  icon?: React.ReactNode;
}

export interface MobileShellProps {
  centreName?: string;
  tabs: TabItem[];
  children: React.ReactNode;
  languageSlot?: React.ReactNode;
  onConflictClick?: () => void;
}

export function MobileShell({
  centreName = "CohortOS",
  tabs,
  children,
  languageSlot,
  onConflictClick,
}: MobileShellProps) {
  const { t } = useLocale();

  return (
    <div className="mobile-shell">
      <header className="mobile-header">
        <div className="mobile-centre">{centreName}</div>
        <div className="mobile-header-right">
          {languageSlot}
          <SyncPill onConflictClick={onConflictClick} className="sync-pill-compact" />
        </div>
      </header>

      <main className="mobile-content"><OfflineBanner />{children}</main>

      <nav className="mobile-tabs" aria-label={t("navHome")}>
        {tabs.slice(0, 4).map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`mobile-tab ${tab.active ? "active" : ""}`}
            onClick={tab.onClick}
            aria-current={tab.active ? "page" : undefined}
          >
            {tab.icon && <span className="mobile-tab-icon">{tab.icon}</span>}
            <span className="mobile-tab-label">{tab.label}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}
