import { useCallback, useEffect, useState } from "react";
import {
  loadTokens,
  saveTokens,
  clearTokens,
  ensureSession,
  requestOtp,
  verifyOtp,
  type AuthTokens,
} from "../api/client";

export type AuthState = {
  tokens: Partial<AuthTokens>;
  roles: string[];
  loading: boolean;
  error: string | null;
  isAuthenticated: boolean;
};

function rolesFromTokens(tokens: Partial<AuthTokens>): string[] {
  // JWT roles are not always decoded client-side; screens currently rely on
  // server enforcement. Placeholder until claims decode is added.
  void tokens;
  return [];
}

export function useAuth() {
  const [tokens, setTokens] = useState<Partial<AuthTokens>>(() => loadTokens());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const session = await ensureSession();
      if (session) {
        setTokens(loadTokens());
      } else {
        setTokens({});
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Session check failed");
      setTokens({});
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const loginWithOtp = useCallback(
    async (phone: string, code: string, otpId: string, tenantId?: string) => {
      setError(null);
      const result = await verifyOtp({ otp_id: otpId, code, tenant_id: tenantId });
      saveTokens(result);
      setTokens(loadTokens());
      return result;
    },
    []
  );

  const sendOtp = useCallback(async (phone: string, tenantId?: string) => {
    setError(null);
    return requestOtp({ phone, tenant_id: tenantId });
  }, []);

  const logout = useCallback(async () => {
    clearTokens();
    setTokens({});
  }, []);

  return {
    tokens,
    roles: rolesFromTokens(tokens),
    loading,
    error,
    isAuthenticated: Boolean(tokens.access_token || tokens.refresh_token || (typeof localStorage !== "undefined" && localStorage.getItem("cohortos_refresh_token"))),
    tenantId: tokens.tenant_id || "",
    refresh,
    sendOtp,
    loginWithOtp,
    logout,
    setError,
  } satisfies AuthState & {
    tenantId: string;
    refresh: () => Promise<void>;
    sendOtp: (
      phone: string,
      tenantId?: string
    ) => ReturnType<typeof requestOtp>;
    loginWithOtp: (
      phone: string,
      code: string,
      otpId: string,
      tenantId?: string
    ) => Promise<AuthTokens>;
    logout: () => Promise<void>;
    setError: (e: string | null) => void;
  };
}
