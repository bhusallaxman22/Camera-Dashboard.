"use client";

import { useEffect, useRef } from "react";
import type { PhotoDetail, PhotoUpdate } from "./types";

interface Handlers {
  onUpdate: (body: PhotoUpdate) => void;
  onPrev?: () => void;
  onNext?: () => void;
  /** Extra single-key bindings, keyed by lower-case `KeyboardEvent.key`. */
  extra?: Record<string, () => void>;
}

/** Lightroom-style culling keys: 0–5 rating, P/X/U flag, F favorite, E needs edit, ←/→ navigate. */
export function useCullingKeys(photo: PhotoDetail | undefined, handlers: Handlers) {
  const ref = useRef({ photo, handlers });
  useEffect(() => {
    ref.current = { photo, handlers };
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const { photo: p, handlers: h } = ref.current;
      const target = e.target as HTMLElement | null;
      if (target && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)))
        return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (h.extra?.[k]) h.extra[k]();
      else if (k === "arrowleft" && h.onPrev) h.onPrev();
      else if (k === "arrowright" && h.onNext) h.onNext();
      else if (!p) return;
      else if (/^[0-5]$/.test(k)) h.onUpdate({ rating: Number(k) });
      else if (k === "p") h.onUpdate({ flag: p.flag === "pick" ? "none" : "pick" });
      else if (k === "x") h.onUpdate({ flag: p.flag === "reject" ? "none" : "reject" });
      else if (k === "u") h.onUpdate({ flag: "none" });
      else if (k === "f") h.onUpdate({ favorite: !p.favorite });
      else if (k === "e") h.onUpdate({ needs_edit: !p.needs_edit });
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
