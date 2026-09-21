import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { MobileShell } from "../../shell/MobileShell";
import { LanguageToggle } from "../../components/LanguageToggle";
import { Card } from "../../components/Card";
import { useLocale } from "../../i18n/LocaleContext";
import { listStudentVault, loadTokens } from "../../api/client"
import type { VaultResource, ApiError } from "../../api/client"
import { loadStudentSession, plainAccessReason } from "./studentContext";
import "../../components/LanguageToggle.css";
import "../../shell/MobileShell.css";

/**
 * Student Vault — Portion 21
 * Gated resources show plain-language reason, never just a lock icon.
 */

interface VaultItem {
  resource: VaultResource;
  allowed: boolean;
  reasons: string[];
}

export function StudentVaultScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";
  const session = loadStudentSession();

  const [items, setItems] = useState<VaultItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!session.studentId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await listStudentVault(tenantId, session.studentId);
      setItems(res.items || []);
    } catch (e) {
      setError((e as ApiError).detail || t("networkError"));
    } finally {
      setLoading(false);
    }
  }, [tenantId, session.studentId, t]);

  useEffect(() => {
    load();
  }, [load]);

  const tabs = [
    { id: "home", label: t("navHome"), onClick: () => navigate("/student") },
    { id: "solve", label: t("navSolve"), onClick: () => navigate("/student/solve") },
    { id: "vault", label: t("navVault"), active: true },
    { id: "results", label: t("navResults"), onClick: () => navigate("/student/results") },
  ];

  return (
    <MobileShell centreName={t("appName")} tabs={tabs} languageSlot={<LanguageToggle />}>
      <h1 className="view-title" style={{ fontSize: 22 }}>
        {t("navVault")}
      </h1>
      <p className="caption muted" style={{ marginBottom: 16 }}>
        Resources from your centre. Locked items explain why.
      </p>

      {!session.studentId && (
        <div className="warning-banner" role="status">
          Link your admission on Home to see vault content.
        </div>
      )}
      {error && (
        <div className="warning-banner" role="alert">
          {error}
        </div>
      )}
      {loading && <p className="caption muted">{t("loadingView")}</p>}

      <div className="vault-stack">
        {items.map((it) => {
          const r = it.resource;
          const locked = !it.allowed;
          return (
            <Card key={r.id} variant={locked ? "queue-flagged" : "standard"}>
              <div className="vault-row-top">
                <strong>{r.title || "Resource"}</strong>
                <span className="caption">{r.topic || r.resource_type}</span>
              </div>
              {locked ? (
                <div className="gate-reason" role="status">
                  <span className="gate-label">Locked</span>
                  <span>{plainAccessReason(it.reasons)}</span>
                </div>
              ) : (
                <span className="badge badge-attendance-present" role="status">
                  Available
                </span>
              )}
              {Boolean(r.description) && (
                <p className="caption" style={{ marginTop: 8 }}>
                  {String(r.description)}
                </p>
              )}
            </Card>
          );
        })}
        {!loading && session.studentId && items.length === 0 && (
          <p className="caption muted">No resources published yet.</p>
        )}
      </div>

      <style>{`
        .vault-stack { display: grid; gap: 12px; }
        .vault-row-top {
          display: flex;
          justify-content: space-between;
          gap: 10px;
          margin-bottom: 8px;
        }
        .gate-reason {
          display: flex;
          flex-direction: column;
          gap: 4px;
          background: var(--error-bg);
          border-radius: 8px;
          padding: 10px 12px;
          font-size: 14px;
          color: var(--ink);
        }
        .gate-label {
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.05em;
          text-transform: uppercase;
          color: var(--error);
        }
      `}</style>
    </MobileShell>
  );
}
