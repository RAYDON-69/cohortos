/**
 * Unified Vault viewer entry — PDF (pdfjs-dist), image lightbox, Plyr A/V.
 */
import { useEffect, useRef, useState } from "react";
import { getApiBaseUrl, ensureAccessToken, tenantPath } from "../api/client";
import { Button } from "./ui/button";
import { cn } from "../lib/utils";

type Props = {
  tenantId: string;
  resourceId: string;
  title?: string;
  contentType?: string;
  onClose?: () => void;
};

type Kind = "pdf" | "image" | "video" | "audio" | "other";

export function FileViewer({ tenantId, resourceId, title, contentType, onClose }: Props) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState<Kind>("other");
  const [pdfPage, setPdfPage] = useState(1);
  const [pdfPages, setPdfPages] = useState(0);
  const [zoom, setZoom] = useState(1.25);
  const [searchQ, setSearchQ] = useState("");
  const [searchHits, setSearchHits] = useState(0);
  const [pdfMode, setPdfMode] = useState<"pdfjs" | "iframe" | null>(null);
  const [imgScale, setImgScale] = useState(1);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mediaRef = useRef<HTMLDivElement>(null);
  const pdfDocRef = useRef<any>(null);
  const plyrRef = useRef<any>(null);

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
        if (len > 25 * 1024 * 1024) throw new Error("File is larger than 25MB");
        const ct = (contentType || res.headers.get("content-type") || "").toLowerCase();
        const blob = await res.blob();
        if (blob.size > 25 * 1024 * 1024) throw new Error("File is larger than 25MB");
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
        const isPdf = ct.includes("pdf") || (title || "").toLowerCase().endsWith(".pdf");
        if (isPdf) {
          setKind("pdf");
          try {
            const pdfjs = await import("pdfjs-dist");
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
      try {
        plyrRef.current?.destroy?.();
      } catch {
        /* */
      }
    };
  }, [tenantId, resourceId, contentType, title]);

  useEffect(() => {
    if (pdfMode !== "pdfjs" || !pdfDocRef.current || !canvasRef.current) return;
    let cancelled = false;
    (async () => {
      try {
        const page = await pdfDocRef.current.getPage(pdfPage);
        const viewport = page.getViewport({ scale: zoom });
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
  }, [pdfMode, pdfPage, zoom]);

  useEffect(() => {
    if (!url || (kind !== "video" && kind !== "audio") || !mediaRef.current) return;
    let cancelled = false;
    (async () => {
      try {
        const Plyr = (await import("plyr")).default;
        await import("plyr/dist/plyr.css");
        if (cancelled) return;
        const el = mediaRef.current!.querySelector("video, audio") as HTMLElement | null;
        if (!el) return;
        plyrRef.current = new Plyr(el, {
          controls: [
            "play-large",
            "play",
            "progress",
            "current-time",
            "mute",
            "volume",
            "settings",
            "fullscreen",
          ],
          settings: ["speed"],
          speed: { selected: 1, options: [0.5, 0.75, 1, 1.25, 1.5, 2] },
        });
      } catch {
        /* native controls remain */
      }
    })();
    return () => {
      cancelled = true;
      try {
        plyrRef.current?.destroy?.();
      } catch {
        /* */
      }
    };
  }, [url, kind]);

  async function runPdfSearch() {
    if (!pdfDocRef.current || !searchQ.trim()) {
      setSearchHits(0);
      return;
    }
    let hits = 0;
    const q = searchQ.toLowerCase();
    for (let i = 1; i <= pdfDocRef.current.numPages; i++) {
      const page = await pdfDocRef.current.getPage(i);
      const tc = await page.getTextContent();
      const text = (tc.items || []).map((it: any) => it.str || "").join(" ").toLowerCase();
      if (text.includes(q)) {
        hits++;
        if (hits === 1) setPdfPage(i);
      }
    }
    setSearchHits(hits);
  }

  return (
    <div
      className="fixed inset-0 z-[1000] flex flex-col bg-ink/60 p-3 md:p-4"
      data-testid="file-viewer"
      role="dialog"
      aria-modal="true"
      aria-label={title || "View file"}
    >
      <div className="flex flex-1 flex-col overflow-hidden rounded-card bg-white shadow-soft">
        <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
          <strong className="flex-1 truncate text-ink">{title || "View file"}</strong>
          {pdfMode === "pdfjs" && (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Button size="sm" variant="outline" disabled={pdfPage <= 1} onClick={() => setPdfPage((p) => Math.max(1, p - 1))}>
                Prev
              </Button>
              <span className="text-slate-700">
                {pdfPage} / {pdfPages}
              </span>
              <Button
                size="sm"
                variant="outline"
                disabled={pdfPage >= pdfPages}
                onClick={() => setPdfPage((p) => Math.min(pdfPages, p + 1))}
              >
                Next
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}>
                −
              </Button>
              <span className="text-xs text-slate-500">{Math.round(zoom * 100)}%</span>
              <Button size="sm" variant="ghost" onClick={() => setZoom((z) => Math.min(3, z + 0.25))}>
                +
              </Button>
              <input
                className="h-9 w-32 rounded-md border border-border-strong px-2 text-sm"
                placeholder="Search in PDF"
                value={searchQ}
                onChange={(e) => setSearchQ(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && void runPdfSearch()}
              />
              <Button size="sm" variant="secondary" onClick={() => void runPdfSearch()}>
                Find
              </Button>
              {searchHits > 0 && <span className="text-xs text-slate-500">{searchHits} page(s)</span>}
            </div>
          )}
          {kind === "image" && (
            <div className="flex gap-1">
              <Button size="sm" variant="ghost" onClick={() => setImgScale((s) => Math.max(0.5, s - 0.25))}>
                Zoom out
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setImgScale((s) => Math.min(4, s + 0.25))}>
                Zoom in
              </Button>
            </div>
          )}
          <Button size="sm" variant="outline" onClick={onClose}>
            Close
          </Button>
        </div>
        <div className="flex-1 overflow-auto p-3">
          {error && (
            <p role="alert" data-testid="viewer-error" className="text-error">
              {error}
            </p>
          )}
          {!error && !url && <p className="text-sm text-slate-500">Loading…</p>}
          {url && kind === "pdf" && pdfMode === "pdfjs" && (
            <canvas ref={canvasRef} data-testid="pdf-canvas" className="mx-auto block max-w-full" />
          )}
          {url && kind === "pdf" && pdfMode === "iframe" && (
            <iframe title={title || "PDF"} src={url} className="h-[70vh] w-full border-0" />
          )}
          {url && kind === "image" && (
            <div className="flex min-h-[50vh] items-center justify-center overflow-auto bg-cream-100">
              <img
                src={url}
                alt={title || "Image"}
                data-testid="viewer-image"
                className={cn("transition-transform duration-150")}
                style={{ transform: `scale(${imgScale})`, transformOrigin: "center center" }}
              />
            </div>
          )}
          {url && kind === "video" && (
            <div ref={mediaRef} data-testid="viewer-video">
              <video src={url} controls className="w-full max-h-[75vh]" playsInline />
            </div>
          )}
          {url && kind === "audio" && (
            <div ref={mediaRef} className="py-8" data-testid="viewer-audio">
              <audio src={url} controls className="w-full" />
            </div>
          )}
          {url && kind === "other" && (
            <p>
              Preview not available.{" "}
              <a className="text-sage-700 underline" href={url} download>
                Download
              </a>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
