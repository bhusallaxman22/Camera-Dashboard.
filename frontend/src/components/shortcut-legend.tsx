"use client";

import { Keyboard } from "lucide-react";
import { useState } from "react";
import { Button } from "./ui/button";

export const CULL_SHORTCUTS: [string, string][] = [
  ["0–5", "Rating"],
  ["P", "Pick"],
  ["X", "Reject"],
  ["U", "Unflag"],
  ["F", "Favorite"],
  ["E", "Needs edit"],
];

/**
 * Keyboard legend toggle, laid out inline so it can sit at the end of an action row; the legend
 * wraps onto its own line. Hidden on touch screens where there is no keyboard to teach.
 */
export function ShortcutLegend({ shortcuts }: { shortcuts: [string, string][] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="contents pointer-coarse:hidden">
      <Button
        size="sm"
        variant="ghost"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label="Keyboard shortcuts"
        active={open}
        title="Keyboard shortcuts"
        className="px-2"
      >
        <Keyboard className="size-4" />
      </Button>
      {open && (
        <dl className="text-ink-200 mt-1 flex basis-full flex-wrap gap-x-4 gap-y-1.5 text-xs">
          {shortcuts.map(([k, label]) => (
            <div key={k} className="flex items-center gap-1.5">
              <dt>
                <kbd className="bg-ink-800 text-ink-100 rounded px-1.5 py-0.5 font-mono">{k}</kbd>
              </dt>
              <dd>{label}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
