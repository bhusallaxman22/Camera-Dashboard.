"use client";

import { useRef, useState, type MouseEvent, type PointerEvent } from "react";

export type SwipeDir = "left" | "right";

interface Options {
  onSwipe: (dir: SwipeDir) => void;
  /** Return false at the ends of a sequence; the drag then rubber-bands instead of committing. */
  canSwipe?: (dir: SwipeDir) => boolean;
  enabled?: boolean;
}

interface Track {
  id: number;
  x: number;
  y: number;
  t: number;
  axis: "x" | "y" | null;
}

const SLOP = 8;

/**
 * Horizontal swipe for touch and pen. The element must carry `touch-action: pan-y`
 * so vertical scrolling stays native; mouse input is ignored (desktop uses arrows).
 */
export function useSwipe({ onSwipe, canSwipe, enabled = true }: Options) {
  const [dx, setDx] = useState(0);
  const track = useRef<Track | null>(null);
  const width = useRef(320);
  const suppressClickUntil = useRef(0);

  const reset = () => {
    track.current = null;
    setDx(0);
  };

  const allowed = (dir: SwipeDir) => canSwipe?.(dir) !== false;

  const handlers = {
    onPointerDown(e: PointerEvent<HTMLElement>) {
      if (!enabled || e.pointerType === "mouse") return;
      if (!e.isPrimary) return reset();
      track.current = { id: e.pointerId, x: e.clientX, y: e.clientY, t: e.timeStamp, axis: null };
      width.current = e.currentTarget.clientWidth || 320;
    },
    onPointerMove(e: PointerEvent<HTMLElement>) {
      const s = track.current;
      if (!s || e.pointerId !== s.id) return;
      const mx = e.clientX - s.x;
      const my = e.clientY - s.y;
      if (!s.axis) {
        if (Math.abs(mx) < SLOP && Math.abs(my) < SLOP) return;
        s.axis = Math.abs(mx) > Math.abs(my) * 1.2 ? "x" : "y";
      }
      if (s.axis !== "x") return;
      setDx(allowed(mx < 0 ? "left" : "right") ? mx : mx * 0.25);
    },
    onPointerUp(e: PointerEvent<HTMLElement>) {
      const s = track.current;
      if (!s || e.pointerId !== s.id) return;
      reset();
      if (s.axis !== "x") return;
      const mx = e.clientX - s.x;
      const velocity = Math.abs(mx) / Math.max(1, e.timeStamp - s.t);
      const dir: SwipeDir = mx < 0 ? "left" : "right";
      suppressClickUntil.current = performance.now() + 400;
      const far = Math.abs(mx) > Math.min(90, width.current * 0.22);
      const flick = Math.abs(mx) > 30 && velocity > 0.45;
      if ((far || flick) && allowed(dir)) onSwipe(dir);
    },
    onPointerCancel: reset,
    onClickCapture(e: MouseEvent<HTMLElement>) {
      if (performance.now() < suppressClickUntil.current) {
        e.preventDefault();
        e.stopPropagation();
      }
    },
  };

  return { dx, dragging: dx !== 0, handlers };
}
