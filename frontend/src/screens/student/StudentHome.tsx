import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { MobileShell } from "../../shell/MobileShell";
import { LanguageToggle } from "../../components/LanguageToggle";
import { Card } from "../../components/Card";
import { Button } from "../../components/Button";
import { FormField, TextInput } from "../../components/FormField";
import { useLocale } from "../../i18n/LocaleContext";
import { createStudentAccount, linkByJoinCode, getStudentHome, loadTokens } from "../../api/client"
import type { StudentHomeView, ApiError } from "../../api/client"
import {
  loadStudentSession,
  saveStudentSession,
  plainAccessReason,
} from "./studentContext";
import "../../components/Button.css";
import "../../components/Card.css";
import "../../components/FormField.css";
import "../../components/LanguageToggle.css";
import "../../shell/MobileShell.css";

/**
 * Student Home — Portion 21
 * MobileShell bottom tabs. Attendance / fees / results summary.
 * Join-code claim when unlinked.
 */

export function StudentHomeScreen() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const tokens = loadTokens();
  const tenantId = tokens.tenant_id || "demo-tenant";
  const session = loadStudentSession();

  const [view, setView] = useState<StudentHomeView | null>(null);
  const [joinCode, setJoinCode] = useState("");
  const [phone, setPhone] = useState("");
  const [loading, setLoading] = useState(!!session.accountId);
  const [linking, setLinking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const s = loadStudentSession();
    if (!s.accountId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const home = await getStudentHome(tenantId, s.accountId);
      setView(home);
      if (home.admission_id) {
        saveStudentSession({
          accountId: s.accountId,
          studentId: home.admission_id,
          studentName: home.student?.name,
          roll: home.student?.roll,
        });
      }
    } catch (e) {
      const err = e as ApiError;
      setError(err.detail || t("networkError"));
      if (err.status === 403) {
        // unlinked
        setView(null);
      }
    } finally {
      setLoading(false);
    }
  }, [tenantId, t]);

  useEffect(() => {
    load();
  }, [load]);

  async function onClaim() {
    if (!joinCode.trim()) return;
    setLinking(true);
    setError(null);
    try {
      let accountId = loadStudentSession().accountId;
      if (!accountId) {
        const created = await createStudentAccount(tenantId, {
          phone: phone || "01000000000",
          display_name: "Student",
        });
        accountId = created.account.id;
      }
      const linked = await linkByJoinCode(tenantId, accountId, joinCode.trim());
      saveStudentSession({
        accountId,
        studentId: linked.admission_id,
        studentName: linked.student_name,
        roll: linked.roll,
      });
      setJoinCode("");
      await load();
    } catch (e) {
      setError((e as ApiError).detail || t("genericError"));
    } finally {
      setLinking(false);
    }
  }

  const tabs = [
    { id: "home", label: t("navHome"), active: true },
    { id: "solve", label: t("navSolve"), onClick: () => navigate("/student/solve") },
    { id: "vault", label: t("navVault"), onClick: () => navigate("/student/vault") },
    { id: "results", label: t("navResults"), onClick: () => navigate("/student/results") },
  ];

  const s = loadStudentSession();
  const recentAtt = (view?.attendance || []).slice(-5).reverse();
  const recentPay = (view?.payments || []).slice(-3).reverse();
  const recentRes = (view?.results || []).slice(0, 3);

  return (
    <MobileShell centreName={t("appName")} tabs={tabs} languageSlot={<LanguageToggle />}>
      <h1 className="view-title" style={{ fontSize: 22 }}>
        {s.studentName || t("navHome")}
      </h1>
      {s.roll && (
        <p className="caption muted" style={{ marginBottom: 16 }}>
          Roll {s.roll}
        </p>
      )}

      {error && (
        <div className="warning-banner" role="alert" style={{ marginBottom: 12 }}>
          {error}
        </div>
      )}

      {!s.studentId && (
        <Card variant="featured">
          <div className="eyebrow">Link your admission</div>
          <p className="caption" style={{ marginBottom: 12 }}>
            Enter the join code from your centre. Staff can also link you manually.
          </p>
          <FormField id="phone" label="Phone (for new account)">
            <TextInput id="phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </FormField>
          <FormField id="join" label="Join code" required>
            <TextInput
              id="join"
              value={joinCode}
              onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
              placeholder="ABCD12"
            />
          </FormField>
          <Button
            variant="primary"
            onClick={() => void onClaim()}
            loading={linking}
            disabled={!joinCode.trim()}
          >
            Claim with join code
          </Button>
        </Card>
      )}

      {loading && <p className="caption muted">{t("loadingView")}</p>}

      {s.studentId && view && (
        <div className="home-stack">
          <Card>
            <div className="eyebrow">Attendance (recent)</div>
            {recentAtt.length === 0 && (
              <p className="caption muted">No attendance records yet.</p>
            )}
            <ul className="mini-list">
              {recentAtt.map((a, i) => (
                <li key={i}>
                  <span className="mono-data">{a.date || "—"}</span>
                  <span
                    className={`badge badge-attendance-${a.status || "absent"}`}
                    role="status"
                  >
                    {a.status || "—"}
                  </span>
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <div className="eyebrow">Fees</div>
            {recentPay.length === 0 && (
              <p className="caption muted">No payment records yet.</p>
            )}
            <ul className="mini-list">
              {recentPay.map((p, i) => (
                <li key={i}>
                  <span className="mono-data">
                    {p.year}-{String(p.month).padStart(2, "0")}
                  </span>
                  <span
                    className={
                      p.status === "paid" || p.status === "locked"
                        ? "badge badge-payment-locked"
                        : "badge badge-payment-due"
                    }
                    role="status"
                  >
                    {p.status || "—"}
                  </span>
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <div className="eyebrow">Results</div>
            {recentRes.length === 0 && (
              <p className="caption muted">No results yet.</p>
            )}
            <ul className="mini-list">
              {recentRes.map((r, i) => (
                <li key={i}>
                  <span>{r.chapter_or_topic || r.exam_date || "Exam"}</span>
                  <span className="mono-data">
                    {r.is_absent ? "Absent" : `${r.percentage ?? "—"}%`}
                  </span>
                </li>
              ))}
            </ul>
            <Button size="sm" variant="outline" onClick={() => navigate("/student/results")}>
              Full history
            </Button>
          </Card>
        </div>
      )}

      <style>{`
        .home-stack { display: grid; gap: 14px; }
        .mini-list {
          list-style: none;
          margin: 8px 0 12px;
          padding: 0;
        }
        .mini-list li {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 10px;
          padding: 8px 0;
          border-bottom: 1px solid var(--border);
          font-size: 14px;
        }
      `}</style>
    </MobileShell>
  );
}
