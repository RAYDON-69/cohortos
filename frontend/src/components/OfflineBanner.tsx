import { useConnectivity } from "../hooks/useConnectivity";

export function OfflineBanner() {
  const { state } = useConnectivity();
  if (state !== "offline") return null;
  return (
    <div
      className="mb-3 rounded-md border border-border-strong bg-sage-100 px-3 py-2 text-sm text-sage-900"
      role="status"
    >
      You are offline. Changes are saved on this device and will sync when you reconnect.
    </div>
  );
}
