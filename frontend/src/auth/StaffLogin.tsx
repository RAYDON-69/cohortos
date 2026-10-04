/**
 * Staff Login — modern product surface (Phase 8).
 * Logic unchanged: phone OTP, trial, multi-centre; Framer Motion + Tailwind hierarchy.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { useLocale } from "../i18n/LocaleContext";
import { useAuth } from "../hooks/useAuth";
import {
  ensureSession,
  requestOtp as apiRequestOtp,
  startCentreTrial,
} from "../api/client";

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
    if (isAuthenticated) navigate("/attendance", { replace: true });
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
        setInfo(`Pilot mode — your login code is ${res._test_code}. (Real SMS comes later.)`);
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
    <div
      role="main" aria-label="Sign in" className="min-h-screen flex items-center justify-center p-6 bg-gradient-to-br from-cream via-sage-100 to-peri-bg"
      data-testid="staff-login"
    >
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
        className="w-full max-w-md"
      >
        <Card className="border-border shadow-soft overflow-hidden">
          <CardHeader className="space-y-2 pb-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-800">
              Coaching desk
            </p>
            <CardTitle className="font-display text-3xl tracking-tight">
              <h1 className="text-3xl font-semibold tracking-tight m-0">{t("appName") || "CohortOS"}</h1>
            </CardTitle>
            <CardDescription className="text-base text-slate-800">
              {mode === "login"
                ? "Welcome back — sign in with your phone to open the desk"
                : "Create your coaching centre in a few minutes"}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 pt-2">
            <AnimatePresence mode="wait">
              {error && (
                <motion.div
                  key="err"
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  className="rounded-md bg-error-bg border border-error/30 text-error px-3 py-2 text-sm flex items-start justify-between gap-2"
                  role="alert"
                >
                  <span>{error}</span>
                  <Button variant="ghost" size="sm" onClick={() => setError(null)} aria-label="Dismiss">
                    Dismiss
                  </Button>
                </motion.div>
              )}
            </AnimatePresence>
            {info && (
              <div className="rounded-md bg-peri-bg text-peri-text px-3 py-2 text-sm" role="status">
                {info}
              </div>
            )}

            {mode === "login" ? (
              <div className="space-y-3">
                {!otpId && centres.length === 0 && (
                  <>
                    <div className="space-y-1.5">
                      <label className="text-sm font-semibold" htmlFor="staff-phone">
                        Phone
                      </label>
                      <Input
                        id="staff-phone"
                        type="tel"
                        value={phone}
                        onChange={(e) => setPhone(e.target.value)}
                        placeholder="01XXXXXXXXX"
                        disabled={loading}
                        autoComplete="tel"
                      />
                    </div>
                    <Button
                      type="button"
                      className="w-full"
                      disabled={loading || phone.trim().length < 8}
                      onClick={() => void onRequestOtp()}
                    >
                      {loading ? "Sending…" : "Send login code"}
                    </Button>
                  </>
                )}
                {centres.length > 1 && (
                  <div className="space-y-2">
                    <p className="text-sm font-semibold">Choose centre</p>
                    {centres.map((c) => (
                      <Button
                        key={c.tenant_id}
                        variant="outline"
                        className="w-full justify-start"
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
                  <motion.div
                    initial={{ opacity: 0, x: 8 }}
                    animate={{ opacity: 1, x: 0 }}
                    className="space-y-3"
                  >
                    <div className="space-y-1.5">
                      <label className="text-sm font-semibold" htmlFor="staff-otp">
                        6-digit code
                      </label>
                      <Input
                        id="staff-otp"
                        inputMode="numeric"
                        value={code}
                        onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                        placeholder="••••••"
                        disabled={loading}
                        className="tracking-[0.35em] text-center text-lg font-mono"
                      />
                    </div>
                    <Button
                      className="w-full"
                      disabled={loading || code.length < 4}
                      onClick={() => void onVerifyOtp()}
                    >
                      {loading ? "Signing in…" : "Sign in"}
                    </Button>
                    <Button
                      variant="ghost"
                      className="w-full"
                      onClick={() => {
                        setOtpId(null);
                        setCode("");
                      }}
                    >
                      Use a different phone
                    </Button>
                  </motion.div>
                )}
                <p className="text-center text-sm text-slate-700 pt-2">
                  New centre?{" "}
                  <button
                    type="button"
                    className="font-semibold text-sage-700 underline-offset-2 hover:underline"
                    onClick={() => setMode("trial")}
                  >
                    Start free trial
                  </button>
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {(
                  [
                    ["trial-centre", "Centre name", centreName, setCentreName, "text"],
                    ["trial-phone", "Owner phone", phone, setPhone, "tel"],
                    ["trial-owner", "Owner name", ownerName, setOwnerName, "text"],
                    ["trial-email", "Owner email (optional)", ownerEmail, setOwnerEmail, "email"],
                    ["trial-students", "Approx. students", studentCount, setStudentCount, "number"],
                  ] as const
                ).map(([id, label, val, set, type]) => (
                  <div key={id} className="space-y-1.5">
                    <label className="text-sm font-semibold" htmlFor={id}>
                      {label}
                    </label>
                    <Input
                      id={id}
                      type={type}
                      value={val}
                      onChange={(e) => set(e.target.value)}
                      disabled={loading}
                    />
                  </div>
                ))}
                <Button
                  className="w-full"
                  disabled={loading || !centreName.trim() || !phone.trim()}
                  onClick={() => void onStartTrial()}
                >
                  {loading ? "Creating…" : "Create trial centre"}
                </Button>
                <Button variant="ghost" className="w-full" onClick={() => setMode("login")}>
                  Back to sign in
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
        <p className="text-center text-xs text-slate-500 mt-4">
          Offline-first desk for coaching centres
        </p>
      </motion.div>
    </div>
  );
}
