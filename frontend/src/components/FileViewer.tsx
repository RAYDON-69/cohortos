/**
 * Vault FileViewer — feature bar vs Drive/Acrobat/Notion/YouTube-class players (Phase 9).
 * Single entry for PDF / image / video / audio.
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { getApiBaseUrl, ensureAccessToken, tenantPath } from "../api/client";
import { Button } from "./ui/button";
import { cn } from "../lib/utils";

type Props = {
  tenantId: string;
  resourceId: string;
  title?: string;
  contentType?: string;
  onClose?: () => void;
  /** Sibling resource ids for image next/prev */
  siblingIds?: string[];
  onNavigateSibling?: (id: string) => void;
};

type Kind = "pdf" | "image" | "video" | "audio" | "other";

export function FileViewer({
  tenantId,
  resourceId,
  title,
  contentType,
  onClose,
  siblingIds = [],
  onNavigateSibling,
}: Props) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState<Kind>("other");
  const [pdfPage, setPdfPage] = useState(1);
  const [pdfPages, setPdfPages] = useState(0);
  const [zoom, setZoom] = useState(1.25);
  const [rotation, setRotation] = useState(0);
  const [searchQ, setSearchQ] = useState("");
  const [searchMatches, setSearchMatches] = useState<number[]>([]);
  const [matchIdx, setMatchIdx] = useState(0);
  const [pdfMode, setPdfMode] = useState<"pdfjs" | "iframe" | null>(null);
  const [scrollMode, setScrollMode] = useState<"single" | "continuous">("single");
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [outline, setOutline] = useState<{ title: string; page: number }[]>([]);
  const [thumbs, setThumbs] = useState<{ page: number; dataUrl: string }[]>([]);
  const [showThumbs, setShowThumbs] = useState(false);
  const [imgScale, setImgScale] = useState(1);
  const [imgPan, setImgPan] = useState({ x: 0, y: 0 });
  const [fitMode, setFitMode] = useState<"fit" | "actual">("fit");
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textLayerRef = useRef<HTMLDivElement>(null);
  const pinchRef = useRef<{ dist: number; zoom: number } | null>(null);
  const [highlightAll, setHighlightAll] = useState(false);
  const [thumbVtt, setThumbVtt] = useState<string | null>(null);
  const continuousRef = useRef<HTMLDivElement>(null);
  const mediaRef = useRef<HTMLDivElement>(null);
  const pdfDocRef = useRef<any>(null);
  const plyrRef = useRef<any>(null);
  const dragRef = useRef<{ x: number; y: number } | null>(null);

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
            try {
              const ol = await doc.getOutline();
              if (ol?.length) {
                const items: { title: string; page: number }[] = [];
                const walk = async (nodes: any[], depth = 0) => {
                  for (const n of nodes || []) {
                    let page = 1;
                    try {
                      if (n.dest) {
                        const d = typeof n.dest === "string" ? await doc.getDestination(n.dest) : n.dest;
                        if (d?.[0]) {
                          const idx = await doc.getPageIndex(d[0]);
                          page = idx + 1;
                        }
                      }
                    } catch {
                      /* */
                    }
                    items.push({ title: `${"  ".repeat(depth)}${n.title || "Section"}`, page });
                    if (n.items?.length) await walk(n.items, depth + 1);
                  }
                };
                await walk(ol);
                setOutline(items.slice(0, 80));
              }
            } catch {
              setOutline([]);
            }
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

  const renderPage = useCallback(async (pageNum: number, target: HTMLCanvasElement, scale: number, rot: number) => {
    if (!pdfDocRef.current) return;
    const page = await pdfDocRef.current.getPage(pageNum);
    const viewport = page.getViewport({ scale, rotation: rot });
    const ctx = target.getContext("2d");
    target.height = viewport.height;
    target.width = viewport.width;
    await page.render({ canvasContext: ctx, viewport }).promise;
  }, []);

  useEffect(() => {
    if (pdfMode !== "pdfjs" || !pdfDocRef.current || scrollMode !== "single" || !canvasRef.current) return;
    let cancelled = false;
    (async () => {
      await renderPage(pdfPage, canvasRef.current!, zoom, rotation);
      if (cancelled || !textLayerRef.current || !pdfDocRef.current) return;
      try {
        const pdfjs = await import("pdfjs-dist");
        const page = await pdfDocRef.current.getPage(pdfPage);
        const viewport = page.getViewport({ scale: zoom, rotation });
        const layer = textLayerRef.current;
        layer.innerHTML = "";
        layer.style.width = `${viewport.width}px`;
        layer.style.height = `${viewport.height}px`;
        // pdfjs v4: TextLayer class
        const textContent = await page.getTextContent();
        if ((pdfjs as any).TextLayer) {
          const tl = new (pdfjs as any).TextLayer({
            textContentSource: textContent,
            container: layer,
            viewport,
          });
          await tl.render();
        } else if ((pdfjs as any).renderTextLayer) {
          await (pdfjs as any).renderTextLayer({
            textContentSource: textContent,
            container: layer,
            viewport,
            textDivs: [],
          }).promise;
        }
        if (highlightAll && searchQ.trim()) {
          const q = searchQ.toLowerCase();
          layer.querySelectorAll("span").forEach((el) => {
            if ((el.textContent || "").toLowerCase().includes(q)) {
              (el as HTMLElement).style.background = "rgba(185, 138, 46, 0.35)";
            }
          });
        }
      } catch (e) {
        console.warn("text layer", e);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pdfMode, pdfPage, zoom, rotation, scrollMode, renderPage, highlightAll, searchQ]);

  useEffect(() => {
    if (pdfMode !== "pdfjs" || scrollMode !== "continuous" || !continuousRef.current || !pdfDocRef.current) return;
    const root = continuousRef.current;
    root.innerHTML = "";
    let cancelled = false;
    (async () => {
      for (let i = 1; i <= pdfDocRef.current.numPages; i++) {
        if (cancelled) break;
        const c = document.createElement("canvas");
        c.className = "mx-auto mb-3 block max-w-full";
        c.dataset.page = String(i);
        root.appendChild(c);
        await renderPage(i, c, zoom, rotation);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pdfMode, scrollMode, zoom, rotation, renderPage, pdfPages]);

  useEffect(() => {
    if (!showThumbs || !pdfDocRef.current) return;
    let cancelled = false;
    (async () => {
      const out: { page: number; dataUrl: string }[] = [];
      for (let i = 1; i <= Math.min(pdfDocRef.current.numPages, 40); i++) {
        if (cancelled) break;
        const page = await pdfDocRef.current.getPage(i);
        const vp = page.getViewport({ scale: 0.2 });
        const c = document.createElement("canvas");
        c.width = vp.width;
        c.height = vp.height;
        await page.render({ canvasContext: c.getContext("2d"), viewport: vp }).promise;
        out.push({ page: i, dataUrl: c.toDataURL() });
      }
      if (!cancelled) setThumbs(out);
    })();
    return () => {
      cancelled = true;
    };
  }, [showThumbs, pdfPages]);

  useEffect(() => {
    if (!url || (kind !== "video" && kind !== "audio") || !mediaRef.current) return;
    let cancelled = false;
    (async () => {
      try {
        const _plyrMod: any = await import("plyr");
        const Plyr = _plyrMod.default ?? _plyrMod;
        await import("plyr/dist/plyr.css");
        if (cancelled) return;
        const el = mediaRef.current!.querySelector("video, audio") as HTMLElement | null;
        if (!el) return;
        const plyrOpts: any = {
          controls: ["play-large", "play", "progress", "current-time", "mute", "volume", "captions", "settings", "pip", "fullscreen"],
          settings: ["speed"],
          speed: { selected: 1, options: [0.5, 0.75, 1, 1.25, 1.5, 2] },
          keyboard: { focused: true, global: true },
        };
        // Native Plyr preview thumbnails — requires VTT+sprite generated at upload (ffmpeg)
        if (thumbVtt) {
          plyrOpts.previewThumbnails = { enabled: true, src: thumbVtt };
        }
        plyrRef.current = new Plyr(el, plyrOpts);
      } catch {
        /* native */
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

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose?.();
      if (kind === "pdf" && pdfMode === "pdfjs") {
        if (e.key === "ArrowRight" || e.key === "PageDown") setPdfPage((p) => Math.min(pdfPages, p + 1));
        if (e.key === "ArrowLeft" || e.key === "PageUp") setPdfPage((p) => Math.max(1, p - 1));
        if (e.key === "+" || e.key === "=") setZoom((z) => Math.min(3, z + 0.25));
        if (e.key === "-") setZoom((z) => Math.max(0.5, z - 0.25));
      }
      if (kind === "image") {
        if (e.key === "+" || e.key === "=") setImgScale((s) => Math.min(4, s + 0.25));
        if (e.key === "-") setImgScale((s) => Math.max(0.5, s - 0.25));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [kind, pdfMode, pdfPages, onClose]);

  async function runPdfSearch() {
    if (!pdfDocRef.current || !searchQ.trim()) {
      setSearchMatches([]);
      return;
    }
    const q = searchQ.toLowerCase();
    const pages: number[] = [];
    for (let i = 1; i <= pdfDocRef.current.numPages; i++) {
      const page = await pdfDocRef.current.getPage(i);
      const tc = await page.getTextContent();
      const text = (tc.items || []).map((it: any) => it.str || "").join(" ").toLowerCase();
      if (text.includes(q)) pages.push(i);
    }
    setSearchMatches(pages);
    setMatchIdx(0);
    if (pages.length) setPdfPage(pages[0]);
  }

  function printPdf() {
    if (!url) return;
    const w = window.open(url);
    w?.print();
  }


  function onPinchStart(e: React.TouchEvent) {
    if (e.touches.length !== 2) return;
    const d = Math.hypot(
      e.touches[0].clientX - e.touches[1].clientX,
      e.touches[0].clientY - e.touches[1].clientY
    );
    pinchRef.current = { dist: d, zoom: kind === "pdf" ? zoom : imgScale };
  }
  function onPinchMove(e: React.TouchEvent) {
    if (e.touches.length !== 2 || !pinchRef.current) return;
    e.preventDefault();
    const d = Math.hypot(
      e.touches[0].clientX - e.touches[1].clientX,
      e.touches[0].clientY - e.touches[1].clientY
    );
    const scale = (d / pinchRef.current.dist) * pinchRef.current.zoom;
    if (kind === "pdf") setZoom(Math.min(3, Math.max(0.5, scale)));
    else if (kind === "image") setImgScale(Math.min(4, Math.max(0.5, scale)));
  }
  function onPinchEnd() {
    pinchRef.current = null;
  }

  const bg = theme === "dark" ? "bg-sage-900 text-white" : "bg-white text-ink";
  const sibIdx = siblingIds.indexOf(resourceId);


  async function openImageLightbox() {
    if (!url || kind !== "image") return;
    try {
      const PhotoSwipe = (await import("photoswipe")).default;
      await import("photoswipe/style.css");
      const img = new Image();
      img.src = url;
      await img.decode().catch(() => undefined);
      const ps = new PhotoSwipe({
        dataSource: [{ src: url, width: img.naturalWidth || 1600, height: img.naturalHeight || 1200, alt: title || "Image" }],
        index: 0,
      });
      ps.init();
    } catch {
      // photoswipe optional at runtime
    }
  }


  return (
    <div className="fixed inset-0 z-[1000] flex flex-col bg-ink/60 p-2 md:p-4" data-testid="file-viewer" role="dialog" aria-modal="true">
      <div className={cn("flex flex-1 flex-col overflow-hidden rounded-card shadow-soft", bg)}>
        <div className="flex flex-wrap items-center gap-1 border-b border-border px-2 py-1.5 text-sm">
          <strong className="mr-2 max-w-[40%] truncate">{title || "View file"}</strong>
          {kind === "pdf" && pdfMode === "pdfjs" && (
            <>
              <Button size="sm" variant="outline" disabled={pdfPage <= 1} onClick={() => setPdfPage((p) => Math.max(1, p - 1))}>Prev</Button>
              <span>{pdfPage}/{pdfPages}</span>
              <Button size="sm" variant="outline" disabled={pdfPage >= pdfPages} onClick={() => setPdfPage((p) => Math.min(pdfPages, p + 1))}>Next</Button>
              <Button size="sm" variant="ghost" onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}>−</Button>
              <span className="text-xs">{Math.round(zoom * 100)}%</span>
              <Button size="sm" variant="ghost" onClick={() => setZoom((z) => Math.min(3, z + 0.25))}>+</Button>
              <Button size="sm" variant="ghost" onClick={() => setRotation((r) => (r + 90) % 360)}>Rotate</Button>
              <Button size="sm" variant="ghost" onClick={() => setScrollMode((m) => (m === "single" ? "continuous" : "single"))}>
                {scrollMode === "single" ? "Continuous" : "Single page"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setShowThumbs((s) => !s)}>Thumbnails</Button>
              <Button size="sm" variant="ghost" onClick={() => setTheme((t) => (t === "light" ? "dark" : "light"))}>Theme</Button>
              <Button size="sm" variant="ghost" onClick={printPdf}>Print</Button>
              <input className="h-8 w-28 rounded border border-border-strong px-2 text-xs text-ink" placeholder="Search" value={searchQ} onChange={(e) => setSearchQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && void runPdfSearch()} />
              <Button size="sm" variant="secondary" onClick={() => void runPdfSearch()}>Find</Button>
              <Button size="sm" variant="ghost" onClick={() => setHighlightAll((h) => !h)}>
                {highlightAll ? "Clear highlight" : "Highlight all"}
              </Button>
              {searchMatches.length > 0 && (
                <>
                  <span className="text-xs">{matchIdx + 1}/{searchMatches.length}</span>
                  <Button size="sm" variant="ghost" onClick={() => { const i = (matchIdx + 1) % searchMatches.length; setMatchIdx(i); setPdfPage(searchMatches[i]); }}>Next hit</Button>
                </>
              )}
            </>
          )}
          {kind === "image" && (
            <>
              <Button size="sm" variant="secondary" data-testid="image-lightbox" onClick={() => void openImageLightbox()}>Lightbox</Button>
              <Button size="sm" variant="ghost" onClick={() => setImgScale((s) => Math.max(0.5, s - 0.25))}>Zoom out</Button>
              <Button size="sm" variant="ghost" onClick={() => setImgScale((s) => Math.min(4, s + 0.25))}>Zoom in</Button>
              <Button size="sm" variant="ghost" onClick={() => { setFitMode((m) => (m === "fit" ? "actual" : "fit")); setImgScale(fitMode === "fit" ? 1 : 1); setImgPan({ x: 0, y: 0 }); }}>
                {fitMode === "fit" ? "Actual size" : "Fit"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setRotation((r) => (r + 90) % 360)}>Rotate</Button>
              {siblingIds.length > 1 && onNavigateSibling && (
                <>
                  <Button size="sm" variant="outline" disabled={sibIdx <= 0} onClick={() => onNavigateSibling(siblingIds[sibIdx - 1])}>Prev file</Button>
                  <Button size="sm" variant="outline" disabled={sibIdx < 0 || sibIdx >= siblingIds.length - 1} onClick={() => onNavigateSibling(siblingIds[sibIdx + 1])}>Next file</Button>
                </>
              )}
            </>
          )}
          <Button size="sm" variant="ghost" onClick={() => document.documentElement.requestFullscreen?.()}>Fullscreen</Button>
          <Button size="sm" variant="outline" onClick={onClose}>Close</Button>
        </div>
        <div className="flex min-h-0 flex-1">
          {kind === "pdf" && (showThumbs || outline.length > 0) && (
            <aside className="w-40 shrink-0 overflow-auto border-r border-border p-2 text-xs">
              {outline.length > 0 && (
                <div className="mb-2">
                  <div className="mb-1 font-semibold">Outline</div>
                  {outline.map((o, i) => (
                    <button key={i} type="button" className="block w-full truncate text-left hover:underline" onClick={() => setPdfPage(o.page)}>
                      {o.title}
                    </button>
                  ))}
                </div>
              )}
              {showThumbs &&
                thumbs.map((th) => (
                  <button key={th.page} type="button" className="mb-1 block w-full" onClick={() => setPdfPage(th.page)}>
                    <img src={th.dataUrl} alt={`Page ${th.page}`} className="w-full rounded border border-border" />
                  </button>
                ))}
            </aside>
          )}
          <div className="min-h-0 flex-1 overflow-auto p-2">
            {error && <p role="alert" className="text-error">{error}</p>}
            {!error && !url && <p className="text-sm opacity-70">Loading…</p>}
            {url && kind === "pdf" && pdfMode === "pdfjs" && scrollMode === "single" && (
              <div
                className="relative mx-auto inline-block max-w-full"
                onTouchStart={onPinchStart}
                onTouchMove={onPinchMove}
                onTouchEnd={onPinchEnd}
              >
                <canvas ref={canvasRef} data-testid="pdf-canvas" className="block max-w-full" />
                <div
                  ref={textLayerRef}
                  data-testid="pdf-text-layer"
                  className="textLayer absolute left-0 top-0 overflow-hidden leading-none"
                  style={{ opacity: 1 }}
                />
              </div>
            )}
            {url && kind === "pdf" && pdfMode === "pdfjs" && scrollMode === "continuous" && (
              <div ref={continuousRef} data-testid="pdf-continuous" />
            )}
            {url && kind === "pdf" && pdfMode === "iframe" && (
              <iframe title={title || "PDF"} src={url} className="h-[70vh] w-full border-0" />
            )}
            {url && kind === "image" && (
              <div
                className="flex min-h-[50vh] cursor-grab items-center justify-center overflow-hidden active:cursor-grabbing"
                onWheel={(e) => {
                  e.preventDefault();
                  setImgScale((s) => Math.min(4, Math.max(0.5, s + (e.deltaY < 0 ? 0.1 : -0.1))));
                }}
                onMouseDown={(e) => {
                  dragRef.current = { x: e.clientX - imgPan.x, y: e.clientY - imgPan.y };
                }}
                onMouseMove={(e) => {
                  if (!dragRef.current) return;
                  setImgPan({ x: e.clientX - dragRef.current.x, y: e.clientY - dragRef.current.y });
                }}
                onMouseUp={() => {
                  dragRef.current = null;
                }}
                onMouseLeave={() => {
                  dragRef.current = null;
                }}
                onTouchStart={onPinchStart}
                onTouchMove={onPinchMove}
                onTouchEnd={onPinchEnd}
              >
                <img
                  src={url}
                  alt={title || "Image"}
                  data-testid="viewer-image"
                  draggable={false}
                  className="max-w-none select-none"
                  style={{
                    transform: `translate(${imgPan.x}px,${imgPan.y}px) scale(${imgScale}) rotate(${rotation}deg)`,
                    maxWidth: fitMode === "fit" ? "100%" : "none",
                  }}
                />
              </div>
            )}
            {url && kind === "video" && (
              <div ref={mediaRef} data-testid="viewer-video">
                <video src={url} controls className="max-h-[75vh] w-full" playsInline />
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
                <a className="underline" href={url} download>
                  Download
                </a>
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
