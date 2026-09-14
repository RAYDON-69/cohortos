import { useEffect, useState } from "react";
import {
  getSyncState,
  setSyncStateListener,
  startConnectivityPoll,
  stopConnectivityPoll,
  type SyncState,
} from "../api/client";

/**
 * Four-state connectivity pill driver (SPEC / offline-first UX).
 * States: offline | syncing | synced | conflict
 */
export function useConnectivity() {
  const [state, setState] = useState<SyncState>(() => getSyncState());

  useEffect(() => {
    setSyncStateListener(setState);
    startConnectivityPoll();
    return () => {
      stopConnectivityPoll();
    };
  }, []);

  return {
    state,
    isOffline: state === "offline",
    isSyncing: state === "syncing",
    isSynced: state === "synced",
    hasConflict: state === "conflict",
  };
}
