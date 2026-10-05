"use client";

import { Maximize2, ScanFace, ZoomIn, ZoomOut } from "lucide-react";
import { useRef, useState, type MouseEvent, type PointerEvent, type WheelEvent } from "react";
import type { Face } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "./ui/button";

interface Props {
  src: string | null;
  alt: string;
  faces?: Face[];
  className?: string;
}

interface View {
  scale: number;
  x: number;
  y: number;
}

const MAX_SCALE = 8;
const FIT: View = { scale: 1, x: 0, y: 0 };

/**
 * Fit-to-screen preview with wheel / double-click zoom and drag-to-pan.
 * "1:1" zooms to the preview's native pixels (2560px long edge).
 * Parents should pass `key={src}` so a new photo starts at fit.
 */
export function ZoomViewer({ src, alt, faces = [], className }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const img = useRef<HTMLImageElement>(null);
  const [view, setView] = useState<View>(FIT);
  const [dragging, setDragging] = useState(false);
  const [showFaces, setShowFaces] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);

  const zoomTo = (next: number, cx = 0, cy = 0) => {
    setView((v) => {
      const scale = Math.max(1, Math.min(MAX_SCALE, next));
      if (scale === 1) return FIT;
      return { scale, x: cx - ((cx - v.x) * scale) / v.scale, y: cy - ((cy - v.y) * scale) / v.scale };
    });
  };

  const nativeScale = () => {
    const el = img.current;
    return el && el.clientWidth ? Math.max(1, el.naturalWidth / el.clientWidth) : 2;
  };

  const relative = (clientX: number, clientY: number) => {
    const rect = box.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return { x: clientX - rect.left - rect.width / 2, y: clientY - rect.top - rect.height / 2 };
  };

  const onWheel = (e: WheelEvent) => {
    if (!src) return;
    const { x, y } = relative(e.clientX, e.clientY);
    zoomTo(view.scale * (e.deltaY < 0 ? 1.2 : 1 / 1.2), x, y);
  };

  const onDoubleClick = (e: MouseEvent) => {
    const { x, y } = relative(e.clientX, e.clientY);
    zoomTo(view.scale > 1 ? 1 : Math.max(2, nativeScale()), x, y);
  };

  const onPointerDown = (e: PointerEvent) => {
    if (view.scale === 1) return;
    (e.target as Element).setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, y: e.clientY, ox: view.x, oy: view.y };
    setDragging(true);
  };
  const onPointerMove = (e: PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    setView((v) => ({ ...v, x: d.ox + e.clientX - d.x, y: d.oy + e.clientY - d.y }));
  };
  const onPointerUp = () => {
    drag.current = null;
    setDragging(false);
  };

  return (
    <div className={cn("checker relative overflow-hidden rounded-xl select-none", className)}>
      <div
        ref={box}
        className={cn(
          "absolute inset-0 grid place-items-center",
          view.scale > 1 ? "cursor-grab active:cursor-grabbing" : "cursor-zoom-in",
        )}
        onWheel={onWheel}
        onDoubleClick={onDoubleClick}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        {src ? (
          <div
            className="relative max-h-full max-w-full"
            style={{
              transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
              transition: dragging ? "none" : "transform 120ms ease-out",
            }}
          >
            <img
              ref={img}
              src={src}
              alt={alt}
              draggable={false}
              onLoad={() => setLoaded(true)}
              className={cn(
                "block max-h-[calc(100vh-11rem)] max-w-full object-contain transition-opacity duration-300",
                loaded ? "opacity-100" : "opacity-0",
              )}
            />
            {showFaces &&
              faces.map((f, i) => (
                <div
                  key={i}
                  className="border-accent/80 pointer-events-none absolute rounded border-2"
                  style={{
                    left: `${f.x * 100}%`,
                    top: `${f.y * 100}%`,
                    width: `${f.w * 100}%`,
                    height: `${f.h * 100}%`,
                  }}
                >
                  {f.sharpness != null && (
                    <span className="bg-accent text-ink-950 absolute -top-5 left-0 rounded px-1 text-[10px] font-bold">
                      {f.sharpness.toFixed(0)}
                    </span>
                  )}
                </div>
              ))}
            {showFaces &&
              faces.flatMap((f, i) =>
                f.eyes.map((e, j) => (
                  <span
                    key={`${i}-${j}`}
                    className={cn(
                      "pointer-events-none absolute size-2 -translate-1/2 rounded-full ring-2",
                      (e.sharpness ?? 0) >= 45 ? "bg-ok ring-ok/40" : "bg-warn ring-warn/40",
                    )}
                    style={{ left: `${e.x * 100}%`, top: `${e.y * 100}%` }}
                  />
                )),
              )}
          </div>
        ) : (
          <div className="text-ink-500 text-sm">Preview not generated yet</div>
        )}
        {src && !loaded && <div className="bg-ink-900/40 absolute inset-0 animate-pulse" />}
      </div>

      {src && (
        <div className="bg-ink-950/80 absolute right-3 bottom-3 flex items-center gap-1 rounded-lg p-1 backdrop-blur">
          {faces.length > 0 && (
            <Button
              size="icon"
              variant="ghost"
              active={showFaces}
              onClick={() => setShowFaces((v) => !v)}
              aria-label="Toggle face overlay"
              title="Faces & eyes"
            >
              <ScanFace className="size-4" />
            </Button>
          )}
          <Button
            size="icon"
            variant="ghost"
            onClick={() => zoomTo(view.scale / 1.5)}
            aria-label="Zoom out"
            disabled={view.scale <= 1}
          >
            <ZoomOut className="size-4" />
          </Button>
          <span className="text-ink-300 tabular w-12 text-center text-[11px]">
            {Math.round(view.scale * 100)}%
          </span>
          <Button
            size="icon"
            variant="ghost"
            onClick={() => zoomTo(view.scale * 1.5)}
            aria-label="Zoom in"
            disabled={view.scale >= MAX_SCALE}
          >
            <ZoomIn className="size-4" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => zoomTo(nativeScale())}
            title="Native preview pixels"
          >
            1:1
          </Button>
          <Button size="icon" variant="ghost" onClick={() => setView(FIT)} aria-label="Fit" title="Fit">
            <Maximize2 className="size-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
