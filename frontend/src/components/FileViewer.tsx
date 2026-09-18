/**
 * Vault file viewer — uses native browser capabilities (no custom renderer).
 * PDF: <iframe> / <object> (Chrome/Edge/Firefox built-in). Images: <img>.
 * For richer PDF UX later: pdfjs-dist (Mozilla, Apache-2.0) is the recommended add-on.
 */
import { useEffect, useState } from "react";
import { getApiBaseUrl, ensureAccessToken, tenantPath } from "../api/client";

type Props = {
  tenantId: string;
  resourceId: string;
  title?: string;
  contentType?: string;
  onClose?: () => void;
};

export function FileViewer({ tenantId, resourceId, title, contentType, onClose }: Props) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState<"pdf" | "image" | "video" | "audio" | "other">("other");

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    (async () => {
      try {
        const token = await ensureAccessToken();
        const res = await fetch(
          `${getApiBaseUrl()}${tenantPath(tenantId, `/vault/${resourceId}/content`)}`,
          { headers: token ? { Authorization: `Bearer ${token}` } : {} }
        );
        if (!res.ok) {
          throw new Error(`Could not open file (${res.status})`);
        }
        const ct = (contentType || res.headers.get("content-type") || "").toLowerCase();
        const blob = await res.blob();
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
        if (ct.includes("pdf") || title?.toLowerCase().endsWith(".pdf")) setKind("pdf");
        else if (ct.startsWith("image/")) setKind("image");
        else if (ct.startsWith("video/")) setKind("video");
        else if (ct.startsWith("audio/")) setKind("audio");
        else setKind("other");
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Open failed");
      }
    })();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [tenantId, resourceId, contentType, title]);

  return (
    <div
      className="file-viewer"
      data-testid="file-viewer"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.55)",
        zIndex: 1000,
        display: "flex",
        flexDirection: "column",
        padding: 16,
      }}
    >
      <div
        style={{
          background: "#fff",
          borderRadius: 8,
          flex: 1,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "8px 12px",
            borderBottom: "1px solid #eee",
          }}
        >
          <strong>{title || "View file"}</strong>
          <button type="button" onClick={onClose}>
            Close
          </button>
        </div>
        <div style={{ flex: 1, overflow: "auto", padding: 8 }}>
          {error && <p role="alert">{error}</p>}
          {!error && !url && <p className="caption muted">Loading…</p>}
          {url && kind === "pdf" && (
            <iframe title={title || "PDF"} src={url} style={{ width: "100%", height: "100%", minHeight: 480, border: 0 }} />
          )}
          {url && kind === "image" && (
            <img src={url} alt={title || "Image"} style={{ maxWidth: "100%", margin: "0 auto", display: "block" }} />
          )}
          {url && kind === "video" && <video src={url} controls style={{ width: "100%", maxHeight: "80vh" }} />}
          {url && kind === "audio" && <audio src={url} controls style={{ width: "100%" }} />}
          {url && kind === "other" && (
            <p>
              Preview not available for this type.{" "}
              <a href={url} download>
                Download instead
              </a>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
