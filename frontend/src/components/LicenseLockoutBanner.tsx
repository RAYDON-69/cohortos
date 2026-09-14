import React from "react";

/**
 * Persistent banner when license lockout is active (Addendum §1.A).
 * Data remains visible; writes are disabled by screens reading data-license-lockout.
 */
export function LicenseLockoutBanner({ reason }: { reason: string | null }) {
  return (
    <div
      className="banner banner-error license-lockout-banner"
      role="alert"
      data-testid="license-lockout-banner"
      style={{
        position: "sticky",
        top: 0,
        zIndex: 50,
        padding: "var(--space-3, 12px) var(--space-4, 16px)",
        background: "var(--error-bg)",
        color: "var(--error)",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <strong>Billing lockout</strong>
      <span style={{ marginLeft: 8 }}>
        {reason ||
          "This centre is past the billing grace window. You can view and export data; all changes are disabled until billing is current."}
      </span>
    </div>
  );
}
