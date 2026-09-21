/**
 * Vault file viewer — pdfjs-dist (Apache-2.0) for PDF when available; native fallback.
 */
import { useEffect, useRef, useState } from "react";
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
  const [pdfPage, setPdfPage] = useState(1);
  const [pdfPages, setPdfPages] = useState(0);
  const [pdfMode, setPdfMode] = useState<"pdfjs" | "iframe" | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pdfDocRef = useRef<any>(null);

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
        if (!res.ok) throw new Error(`Could not open file (${res.status})`);
        const len = Number(res.headers.get("content-length") || 0);
        if (len > 25 * 1024 * 1024) throw new Error("File is larger than 25MB and cannot be opened in the viewer");
        const ct = (contentType || res.headers.get("content-type") || "").toLowerCase();
        const blob = await res.blob();
        if (blob.size > 25 * 1024 * 1024) throw new Error("File is larger than 25MB and cannot be opened in the viewer");
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
        const isPdf = ct.includes("pdf") || (title || "").toLowerCase().endsWith(".pdf");
        if (isPdf) {
          setKind("pdf");
          try {
            const pdfjs = await import("pdfjs-dist");
            // @ts-expect-error worker optional
            if (pdfjs.GlobalWorkerOptions) {
              pdfjs.GlobalWorkerOptions.workerSrc = new URL(
                "pdfjs-dist/build/pdf.worker.min.mjs",
                import.meta.url
              ).toString();
            }
            const data = new Uint8Array(await blob.arrayBuffer());
            const doc = await pdfjs.getDocument({ data }).promise;
            pdfDocRef.current = doc;
            setPdfPages(doc.numPages);
            setPdfPage(1);
            setPdfMode("pdfjs");
          } catch {
            setPdfMode("iframe");
          }
        } else if (ct.startsWith("image/")) setKind("image");
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

  useEffect(() => {
    if (pdfMode !== "pdfjs" || !pdfDocRef.current || !canvasRef.current) return;
    let cancelled = false;
    (async () => {
      try {
        const page = await pdfDocRef.current.getPage(pdfPage);
        const viewport = page.getViewport({ scale: 1.25 });
        const canvas = canvasRef.current!;
        const ctx = canvas.getContext("2d");
        canvas.height = viewport.height;
        canvas.width = viewport.width;
        await page.render({ canvasContext: ctx, viewport }).promise;
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "PDF render failed");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pdfMode, pdfPage]);

  return (
    <div
      className="file-viewer"
      data-testid="file-viewer"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(46, 58, 36, 0.55)",
        zIndex: 1000,
        display: "flex",
        flexDirection: "column",
        padding: 16,
      }}
    >
      <div
        style={{
          background: "var(--white)",
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
            borderBottom: "1px solid var(--border)",
            gap: 8,
          }}
        >
          <strong>{title || "View file"}</strong>
          {pdfMode === "pdfjs" && (
            <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <button type="button" disabled={pdfPage <= 1} onClick={() => setPdfPage((p) => Math.max(1, p - 1))}>
                Prev
              </button>
              <span className="caption">
                {pdfPage} / {pdfPages}
              </span>
              <button
                type="button"
                disabled={pdfPage >= pdfPages}
                onClick={() => setPdfPage((p) => Math.min(pdfPages, p + 1))}
              >
                Next
              </button>
            </span>
          )}
          <button type="button" onClick={onClose}>
            Close
          </button>
        </div>
        <div style={{ flex: 1, overflow: "auto", padding: 8 }}>
          {error && (
            <p role="alert" data-testid="viewer-error">
              {error}
            </p>
          )}
          {!error && !url && <p className="caption muted">Loading…</p>}
          {url && kind === "pdf" && pdfMode === "pdfjs" && (
            <canvas ref={canvasRef} data-testid="pdf-canvas" style={{ maxWidth: "100%", display: "block", margin: "0 auto" }} />
          )}
          {url && kind === "pdf" && pdfMode === "iframe" && (
            <iframe title={title || "PDF"} src={url} style={{ width: "100%", height: "100%", minHeight: 480, border: 0 }} />
          )}
          {url && kind === "image" && (
            <img src={url} alt={title || "Image"} style={{ maxWidth: "100%", margin: "0 auto", display: "block" }} data-testid="viewer-image" />
          )}
          {url && kind === "video" && (
            <video src={url} controls style={{ width: "100%", maxHeight: "80vh" }} data-testid="viewer-video" />
          )}
          {url && kind === "audio" && <audio src={url} controls style={{ width: "100%" }} data-testid="viewer-audio" />}
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
