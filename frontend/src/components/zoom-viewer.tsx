"use client";

import { Maximize2, ScanFace, ZoomIn, ZoomOut } from "lucide-react";
import { useRef, useState, type MouseEvent, type PointerEvent, type WheelEvent } from "react";
import type { Face } from "@/lib/types";
import { useSwipe, type SwipeDir } from "@/lib/use-swipe";
import { cn } from "@/lib/utils";
import { Button } from "./ui/button";

interface Props {
  src: string | null;
  alt: string;
  faces?: Face[];
  className?: string;
  /** Height cap for the fitted image; must match the container height. */
  fitClassName?: string;
  onSwipe?: (dir: SwipeDir) => void;
  canSwipe?: (dir: SwipeDir) => boolean;
  /** Direction the new photo slides in from after a swipe or arrow key. */
  enter?: SwipeDir | null;
}

interface View {
  scale: number;
  x: number;
  y: number;
}

interface Point {
  x: number;
  y: number;
}

const MAX_SCALE = 8;
const FIT: View = { scale: 1, x: 0, y: 0 };

/**
 * Fit-to-screen preview. Desktop: wheel / double-click zoom, drag to pan.
 * Touch: pinch or double-tap to zoom, drag to pan; at fit, swipe sideways to change photo.
 * "1:1" zooms to the preview's native pixels (2560px long edge).
 * Parents should pass `key={src}` so a new photo starts at fit.
 */
export function ZoomViewer({
  src,
  alt,
  faces = [],
  className,
  fitClassName = "max-h-[calc(100svh-11rem)]",
  onSwipe,
  canSwipe,
  enter,
}: Props) {
  const box = useRef<HTMLDivElement>(null);
  const img = useRef<HTMLImageElement>(null);
  const [view, setView] = useState<View>(FIT);
  const [dragging, setDragging] = useState(false);
  const [showFaces, setShowFaces] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [pinching, setPinching] = useState(false);
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);
  const pointers = useRef(new Map<number, Point>());
  const pinch = useRef<{ dist: number; scale: number; center: Point } | null>(null);
  const tapStart = useRef<{ x: number; y: number; t: number } | null>(null);
  const lastTap = useRef<{ x: number; y: number; t: number } | null>(null);
  const lastTouchZoom = useRef(0);

  const swipe = useSwipe({
    onSwipe: (dir) => onSwipe?.(dir),
    canSwipe,
    enabled: Boolean(onSwipe) && view.scale === 1,
  });

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

  const relative = (clientX: number, clientY: number): Point => {
    const rect = box.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return { x: clientX - rect.left - rect.width / 2, y: clientY - rect.top - rect.height / 2 };
  };

  const toggleZoomAt = (clientX: number, clientY: number) => {
    const { x, y } = relative(clientX, clientY);
    zoomTo(view.scale > 1 ? 1 : Math.max(2, nativeScale()), x, y);
  };

  const pinchState = () => {
    const [a = { x: 0, y: 0 }, b = { x: 0, y: 0 }] = [...pointers.current.values()];
    const mid = relative((a.x + b.x) / 2, (a.y + b.y) / 2);
    return { dist: Math.hypot(a.x - b.x, a.y - b.y) || 1, center: mid };
  };

  const onWheel = (e: WheelEvent) => {
    if (!src) return;
    const { x, y } = relative(e.clientX, e.clientY);
    zoomTo(view.scale * (e.deltaY < 0 ? 1.2 : 1 / 1.2), x, y);
  };

  const onDoubleClick = (e: MouseEvent) => {
    if (performance.now() - lastTouchZoom.current < 600) return;
    toggleZoomAt(e.clientX, e.clientY);
  };

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (!src) return;
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (e.isPrimary) tapStart.current = { x: e.clientX, y: e.clientY, t: e.timeStamp };

    if (pointers.current.size === 2) {
      swipe.handlers.onPointerCancel();
      drag.current = null;
      tapStart.current = null;
      pinch.current = { ...pinchState(), scale: view.scale };
      setPinching(true);
      return;
    }
    if (view.scale === 1) {
      swipe.handlers.onPointerDown(e);
      return;
    }
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, y: e.clientY, ox: view.x, oy: view.y };
    setDragging(true);
  };

  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (pointers.current.has(e.pointerId)) pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const p = pinch.current;
    if (p && pointers.current.size === 2) {
      const now = pinchState();
      zoomTo((p.scale * now.dist) / p.dist, p.center.x, p.center.y);
      return;
    }
    const d = drag.current;
    if (d) {
      setView((v) => ({ ...v, x: d.ox + e.clientX - d.x, y: d.oy + e.clientY - d.y }));
      return;
    }
    swipe.handlers.onPointerMove(e);
  };

  const onPointerUp = (e: PointerEvent<HTMLDivElement>) => {
    pointers.current.delete(e.pointerId);
    if (pinch.current) {
      if (pointers.current.size < 2) {
        pinch.current = null;
        setPinching(false);
      }
      setView((v) => (v.scale < 1.05 ? FIT : v));
      return;
    }
    drag.current = null;
    setDragging(false);
    swipe.handlers.onPointerUp(e);

    const t = tapStart.current;
    tapStart.current = null;
    if (e.pointerType === "mouse" || !t) return;
    const isTap = Math.hypot(e.clientX - t.x, e.clientY - t.y) < 10 && e.timeStamp - t.t < 300;
    if (!isTap) return;
    const prev = lastTap.current;
    if (prev && e.timeStamp - prev.t < 320 && Math.hypot(e.clientX - prev.x, e.clientY - prev.y) < 40) {
      lastTap.current = null;
      lastTouchZoom.current = performance.now();
      toggleZoomAt(e.clientX, e.clientY);
    } else {
      lastTap.current = { x: e.clientX, y: e.clientY, t: e.timeStamp };
    }
  };

  const onPointerCancel = (e: PointerEvent<HTMLDivElement>) => {
    pointers.current.delete(e.pointerId);
    pinch.current = null;
    drag.current = null;
    tapStart.current = null;
    setPinching(false);
    setDragging(false);
    swipe.handlers.onPointerCancel();
  };

  const shiftX = view.scale === 1 ? swipe.dx : 0;

  return (
    <div className={cn("checker relative overflow-hidden rounded-xl select-none", className)}>
      <div
        ref={box}
        className={cn(
          "absolute inset-0 grid place-items-center",
          view.scale > 1 ? "cursor-grab active:cursor-grabbing" : "cursor-zoom-in",
        )}
        style={{ touchAction: view.scale > 1 ? "none" : "pan-y" }}
        onWheel={onWheel}
        onDoubleClick={onDoubleClick}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerCancel}
        onClickCapture={swipe.handlers.onClickCapture}
        data-testid="zoom-viewer"
      >
        {src ? (
          <div
            className={cn(
              enter === "left" && "animate-enter-left",
              enter === "right" && "animate-enter-right",
            )}
          >
            <div
              className="relative max-h-full max-w-full"
              style={{
                transform: `translate(${view.x + shiftX}px, ${view.y}px) scale(${view.scale})`,
                transition: dragging || swipe.dragging || pinching ? "none" : "transform 160ms ease-out",
                opacity: shiftX ? Math.max(0.55, 1 - Math.abs(shiftX) / 600) : undefined,
              }}
            >
              <img
                ref={img}
                src={src}
                alt={alt}
                draggable={false}
                onLoad={() => setLoaded(true)}
                className={cn(
                  "block max-w-full object-contain transition-opacity duration-300",
                  fitClassName,
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
                      <span className="bg-accent text-ink-950 absolute -top-6 left-0 rounded px-1 text-xs font-bold">
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
          </div>
        ) : (
          <div className="text-ink-300 text-sm">Preview not generated yet</div>
        )}
        {src && !loaded && <div className="bg-ink-900/40 absolute inset-0 animate-pulse" />}
      </div>

      {src && (
        <div
          className={cn(
            "bg-ink-950/80 absolute right-2 bottom-2 flex items-center gap-1 rounded-lg p-1 backdrop-blur",
            faces.length === 0 && view.scale === 1 && "pointer-coarse:hidden",
          )}
        >
          {faces.length > 0 && (
            <Button
              size="icon"
              variant="ghost"
              active={showFaces}
              aria-pressed={showFaces}
              onClick={() => setShowFaces((v) => !v)}
              aria-label="Show faces and eyes"
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
            className="pointer-coarse:hidden"
          >
            <ZoomOut className="size-4" />
          </Button>
          <span className="text-ink-200 tabular w-12 text-center text-xs pointer-coarse:hidden">
            {Math.round(view.scale * 100)}%
          </span>
          <Button
            size="icon"
            variant="ghost"
            onClick={() => zoomTo(view.scale * 1.5)}
            aria-label="Zoom in"
            disabled={view.scale >= MAX_SCALE}
            className="pointer-coarse:hidden"
          >
            <ZoomIn className="size-4" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => zoomTo(nativeScale())}
            title="Native preview pixels"
            className="pointer-coarse:hidden"
          >
            1:1
          </Button>
          <Button
            size="icon"
            variant="ghost"
            onClick={() => setView(FIT)}
            aria-label="Fit"
            title="Fit"
            className={cn(view.scale === 1 && "pointer-coarse:hidden")}
          >
            <Maximize2 className="size-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
