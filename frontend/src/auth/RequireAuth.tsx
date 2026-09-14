/**
 * Session guard — always renders a recoverable UI (never an empty fragment).
 * Failed/expired session → explicit message + link back to /login (PRD §2).
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ensureSession } from "../api/client";
import { useLicenseLockout } from "../hooks/useLicenseLockout";
import { LicenseLockoutBanner } from "../components/LicenseLockoutBanner";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [authed, setAuthed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const license = useLicenseLockout();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const ok = await ensureSession();
        if (!cancelled) {
          setAuthed(!!ok);
          setReady(true);
        }
      } catch (e) {
        if (!cancelled) {
          setAuthed(false);
          setError(e instanceof Error ? e.message : "Session check failed");
          setReady(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!ready) {
    return (
      <div className="login-page" role="status" aria-live="polite" data-testid="auth-checking">
        <p className="caption muted">Checking session…</p>
      </div>
    );
  }

  if (!authed) {
    return (
      <div className="login-page" role="alert" data-testid="auth-required">
        <div className="login-card">
          <h1 className="view-title">Session required</h1>
          <p className="caption muted">
            {error || "Your session expired or you are not signed in."}
          </p>
          <p style={{ marginTop: 16 }}>
            <Link to="/login" className="btn btn-primary">
              Back to sign in
            </Link>
          </p>
        </div>
      </div>
    );
  }

  return (
    <>
      {license.locked && <LicenseLockoutBanner reason={license.reason} />}
      <div
        data-license-lockout={license.locked ? "true" : "false"}
        className={license.locked ? "license-lockout-root" : undefined}
      >
        {children}
      </div>
    </>
  );
}
