import { useCallback, useEffect, useState } from "react";

/**
 * Observe durable outbox depth for attendance / payments / exams.
 * Until a local IndexedDB/SQLite bridge is exposed to the renderer, this
 * reports 0 and provides a subscribe hook for future wiring.
 */
export function useOfflineQueue() {
  const [depth, setDepth] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const api = (window as unknown as { electronAPI?: { offlineQueueDepth?: () => Promise<number> } })
        .electronAPI;
      if (api?.offlineQueueDepth) {
        const n = await api.offlineQueueDepth();
        setDepth(n);
        return;
      }
    } catch {
      /* ignore */
    }
    setDepth(0);
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), 15_000);
    return () => window.clearInterval(id);
  }, [refresh]);

  return {
    depth,
    hasQueued: depth > 0,
    refresh,
  };
}
