/** Excalidraw whiteboard — FULL tier only; lazy-loaded. */
import { lazy, Suspense, useEffect, useState } from "react";

const ExcalidrawLazy = lazy(async () => {
  try {
    const mod = await import("@excalidraw/excalidraw");
    return { default: mod.Excalidraw as unknown as React.ComponentType<any> };
  } catch {
    return {
      default: function Fallback() {
        return <p>Whiteboard package not installed — run npm i @excalidraw/excalidraw</p>;
      },
    };
  }
});

type Props = {
  sessionId: string;
  tier: "lite" | "full";
  readOnly?: boolean;
  onSave?: (scene: string) => void;
  initialScene?: string;
};

export function WhiteboardPanel({ sessionId, tier, readOnly, onSave, initialScene }: Props) {
  const [scene, setScene] = useState(initialScene || "");
  if (tier === "lite") {
    return (
      <p data-testid="whiteboard-lite-hidden" className="caption muted">
        Whiteboard hidden on LITE tier (4GB / weak network). Switch to FULL to enable.
      </p>
    );
  }
  return (
    <div data-testid="whiteboard-panel" style={{ height: 420, border: "1px solid #ccc" }}>
      <Suspense fallback={<p>Loading whiteboard…</p>}>
        <ExcalidrawLazy
          key={sessionId}
        />
      </Suspense>
      {!readOnly && (
        <button
          type="button"
          onClick={() => onSave?.(scene || "{}")}
        >
          Save scene
        </button>
      )}
    </div>
  );
}
