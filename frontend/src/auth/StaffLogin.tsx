/**
 * Staff Login — extracted from LoginPlaceholder (PRD §2).
 * Phone OTP + JWT; trial onboarding; multi-centre picker.
 * Uses useAuth for session; never leaves a blank protected route.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../components/Button";
import { useLocale } from "../i18n/LocaleContext";
import { useAuth } from "../hooks/useAuth";
import {
  ensureSession,
  requestOtp as apiRequestOtp,
  startCentreTrial,
} from "../api/client";
import "../components/Button.css";

export function StaffLogin() {
  const { t } = useLocale();
  const navigate = useNavigate();
  const { loginWithOtp, isAuthenticated, refresh } = useAuth();

  const [mode, setMode] = useState<"login" | "trial">("login");
  const [phone, setPhone] = useState("");
  const [otpId, setOtpId] = useState<string | null>(null);
  const [tenantId, setTenantId] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [centres, setCentres] = useState<{ tenant_id: string; centre_name: string }[]>([]);
  const [centreName, setCentreName] = useState("");
  const [ownerName, setOwnerName] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [studentCount, setStudentCount] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const ok = await ensureSession();
        if (!cancelled && ok) {
          await refresh();
          navigate("/attendance", { replace: true });
        }
      } catch {
        /* stay on login */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [navigate, refresh]);

  useEffect(() => {
    if (isAuthenticated) {
      navigate("/attendance", { replace: true });
    }
  }, [isAuthenticated, navigate]);

  async function onRequestOtp(selectedTenant?: string) {
    setError(null);
    setInfo(null);
    setLoading(true);
    try {
      const res = await apiRequestOtp({
        phone,
        tenant_id: selectedTenant || tenantId || undefined,
      });
      if (res.centres && res.centres.length > 1) {
        setCentres(res.centres);
        setInfo(res.message || "Choose your centre");
        return;
      }
      if (!res.otp_id) {
        setError(res.message || "Could not send code. Check the phone number.");
        return;
      }
      setOtpId(res.otp_id);
      if (res.tenant_id) setTenantId(res.tenant_id);
      setCentres([]);
      if (res._test_code) {
        setInfo(
          `Pilot mode — your login code is ${res._test_code}. (Real SMS comes later.)`
        );
        setCode(String(res._test_code));
      } else {
        setInfo("Enter the 6-digit code sent to your phone.");
      }
    } catch (e: unknown) {
      const err = e as { detail?: string; message?: string };
      setError(err?.detail || err?.message || "Failed to request OTP");
    } finally {
      setLoading(false);
    }
  }

  async function onVerifyOtp() {
    if (!otpId) return;
    setError(null);
    setLoading(true);
    try {
      await loginWithOtp(phone, code, otpId, tenantId || undefined);
      navigate("/attendance", { replace: true });
    } catch (e: unknown) {
      const err = e as { detail?: string; message?: string };
      setError(err?.detail || err?.message || "Invalid or expired code");
      setCode("");
    } finally {
      setLoading(false);
    }
  }

  async function onStartTrial() {
    setError(null);
    setLoading(true);
    try {
      const res = await startCentreTrial({
        centre_name: centreName,
        owner_phone: phone,
        owner_name: ownerName,
        owner_email: ownerEmail || undefined,
        student_count: studentCount ? Number(studentCount) : 0,
      });
      setTenantId(res.tenant_id);
      setMode("login");
      setInfo("Centre created. Request a login code with the same phone.");
    } catch (e: unknown) {
      const err = e as { detail?: string; message?: string };
      setError(err?.detail || err?.message || "Could not start trial");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page" data-testid="staff-login">
      <div className="login-card">
        <h1 className="view-title">{t("appName") || "CohortOS"}</h1>
        <p className="caption muted">
          {mode === "login"
            ? "Sign in with your phone"
            : "Start a free centre trial"}
        </p>

        {error && (
          <div className="banner banner-error" role="alert">
            {error}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setError(null)}
              aria-label="Dismiss error"
            >
              Dismiss
            </Button>
          </div>
        )}
        {info && (
          <div className="banner banner-info" role="status">
            {info}
          </div>
        )}

        {mode === "login" ? (
          <>
            {!otpId && centres.length === 0 && (
              <div className="form-stack">
                <label className="field-label" htmlFor="staff-phone">
                  Phone
                </label>
                <input
                  id="staff-phone"
                  type="tel"
                  className="field-input"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="01XXXXXXXXX"
                  autoComplete="tel"
                  disabled={loading}
                />
                <Button
                  variant="primary"
                  disabled={loading || !phone.trim()}
                  onClick={() => void onRequestOtp()}
                >
                  {loading ? "Sending…" : "Request code"}
                </Button>
              </div>
            )}

            {centres.length > 1 && (
              <div className="form-stack" role="list">
                <p className="caption">Select centre</p>
                {centres.map((c) => (
                  <Button
                    key={c.tenant_id}
                    variant="outline"
                    onClick={() => {
                      setTenantId(c.tenant_id);
                      void onRequestOtp(c.tenant_id);
                    }}
                  >
                    {c.centre_name}
                  </Button>
                ))}
              </div>
            )}

            {otpId && (
              <div className="form-stack">
                <label className="field-label" htmlFor="staff-otp">
                  6-digit code
                </label>
                <input
                  id="staff-otp"
                  type="text"
                  inputMode="numeric"
                  className="field-input"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  maxLength={6}
                  disabled={loading}
                />
                <Button
                  variant="primary"
                  disabled={loading || code.length < 4}
                  onClick={() => void onVerifyOtp()}
                >
                  {loading ? "Verifying…" : "Verify & sign in"}
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => {
                    setOtpId(null);
                    setCode("");
                  }}
                >
                  Use a different phone
                </Button>
              </div>
            )}

            <p className="caption muted" style={{ marginTop: 24 }}>
              New centre?{" "}
              <button
                type="button"
                className="link-btn"
                onClick={() => setMode("trial")}
              >
                Start free trial
              </button>
            </p>
          </>
        ) : (
          <div className="form-stack">
            <label className="field-label" htmlFor="trial-centre">
              Centre name
            </label>
            <input
              id="trial-centre"
              className="field-input"
              value={centreName}
              onChange={(e) => setCentreName(e.target.value)}
              disabled={loading}
            />
            <label className="field-label" htmlFor="trial-phone">
              Owner phone
            </label>
            <input
              id="trial-phone"
              type="tel"
              className="field-input"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              disabled={loading}
            />
            <label className="field-label" htmlFor="trial-owner">
              Owner name
            </label>
            <input
              id="trial-owner"
              className="field-input"
              value={ownerName}
              onChange={(e) => setOwnerName(e.target.value)}
              disabled={loading}
            />
            <label className="field-label" htmlFor="trial-email">
              Owner email (optional)
            </label>
            <input
              id="trial-email"
              type="email"
              className="field-input"
              value={ownerEmail}
              onChange={(e) => setOwnerEmail(e.target.value)}
              disabled={loading}
            />
            <label className="field-label" htmlFor="trial-students">
              Approx. students
            </label>
            <input
              id="trial-students"
              type="number"
              className="field-input"
              value={studentCount}
              onChange={(e) => setStudentCount(e.target.value)}
              disabled={loading}
            />
            <Button
              variant="primary"
              disabled={loading || !centreName.trim() || !phone.trim()}
              onClick={() => void onStartTrial()}
            >
              {loading ? "Creating…" : "Create trial centre"}
            </Button>
            <Button variant="ghost" onClick={() => setMode("login")}>
              Back to sign in
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
