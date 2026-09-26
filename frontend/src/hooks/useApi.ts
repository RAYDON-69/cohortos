import { useCallback, useState } from "react";
import { apiRequest, type ApiError } from "../api/client";

/**
 * Thin wrapper around apiRequest that maps failures to UI-friendly error state.
 */
export function useApi() {
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const request = useCallback(async <T,>(
    path: string,
    options?: Parameters<typeof apiRequest>[1]
  ): Promise<T | null> => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiRequest<T>(path, options);
      return data;
    } catch (e) {
      const raw = (e as ApiError)?.detail ?? (e instanceof Error ? e.message : e);
      // Never put a non-string into React children (React error #31).
      const detail =
        typeof raw === "string"
          ? raw
          : raw == null
            ? "Request failed"
            : (() => {
                try {
                  return JSON.stringify(raw);
                } catch {
                  return "Request failed";
                }
              })();
      setError(detail);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  return { request, error, loading, setError };
}
