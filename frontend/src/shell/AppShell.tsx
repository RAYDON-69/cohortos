import React from "react";
import { SyncPill } from "../components/SyncPill";
import { OfflineBanner } from "../components/OfflineBanner";
import { useNavigate } from "react-router-dom";
import { useLocale } from "../i18n/LocaleContext";
import { GlobalSearch } from "../components/GlobalSearch";
import { cn } from "../lib/utils";

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
    <div className="flex min-h-screen bg-cream">
      <aside
        className="hidden w-[232px] shrink-0 flex-col border-r border-border bg-white px-3 py-5 md:flex"
        aria-label="Main navigation"
      >
        <button
          type="button"
          className="mb-5 w-full px-2 text-left font-display text-lg font-semibold text-ink"
          onClick={() => navigate("/attendance")}
          title="Back to desk"
        >
          {brand}
        </button>
        <nav className="flex flex-1 flex-col gap-0.5">
          {navItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={cn(
                "flex min-h-10 w-full flex-col items-start rounded-md px-3 py-2.5 text-left text-sm font-medium transition-colors",
                item.active && "bg-sage-700 text-white",
                !item.active && !item.disabled && "text-ink hover:bg-sage-100",
                item.disabled && "cursor-not-allowed text-slate-500"
              )}
              onClick={item.disabled ? undefined : item.onClick}
              disabled={item.disabled}
              title={item.disabled ? item.disabledReason || t("notAvailableForRole") : undefined}
              aria-current={item.active ? "page" : undefined}
            >
              <span>{item.label}</span>
              {item.disabled && (
                <span className="text-[11px] opacity-80">{t("notAvailableForRole")}</span>
              )}
            </button>
          ))}
        </nav>
        {profileSlot && <div className="mt-auto border-t border-border pt-3">{profileSlot}</div>}
      </aside>

      {/* Mobile horizontal nav strip ≤760px */}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex gap-1 overflow-x-auto border-b border-border bg-white px-2 py-2 md:hidden">
          {navItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={cn(
                "shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold whitespace-nowrap",
                item.active ? "bg-sage-700 text-white" : "bg-sage-100 text-sage-900",
                item.disabled && "opacity-40"
              )}
              onClick={item.disabled ? undefined : item.onClick}
              disabled={item.disabled}
            >
              {item.label}
            </button>
          ))}
        </div>

        <header className="flex flex-wrap items-center gap-3 border-b border-border bg-white px-4 py-2">
          <div className="font-mono text-xs text-slate-500">{crumb || ""}</div>
          <div className="min-w-0 flex-1">
            <GlobalSearch />
          </div>
          <div className="flex items-center gap-2">
            {topbarExtra}
            <SyncPill onConflictClick={onConflictClick} />
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-auto p-4 md:p-6">
          <OfflineBanner />
          {children}
        </main>
      </div>
    </div>
  );
}
