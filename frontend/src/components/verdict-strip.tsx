import { percent } from "@/lib/format";
import type { PhotoDetail } from "@/lib/types";
import { cn } from "@/lib/utils";
import { sharpnessTone } from "./analysis-panel";

type Tone = "ok" | "warn" | "bad" | "neutral";

const TONE_TEXT: Record<Tone, string> = {
  ok: "text-ok",
  warn: "text-warn",
  bad: "text-bad",
  neutral: "text-ink-300",
};

interface Cell {
  label: string;
  value: string;
  verdict: string;
  tone: Tone;
}

// Same cut-offs the backend uses for eye warnings (<30 soft) and the local critique (>=45 sharp).
function eyeCell(photo: PhotoDetail): Cell {
  const a = photo.analysis;
  const scores = a?.faces.flatMap((f) => f.eyes.map((e) => e.sharpness)).filter((s) => s != null) ?? [];
  if (!a || a.face_count == null)
    return { label: "Eyes", value: "—", verdict: "Not checked", tone: "neutral" };
  if (!scores.length) {
    return { label: "Eyes", value: "—", verdict: a.face_count ? "Not found" : "No face", tone: "neutral" };
  }
  const best = Math.max(...(scores as number[]));
  const tone: Tone = best >= 45 ? "ok" : best >= 30 ? "warn" : "bad";
  return {
    label: "Eyes",
    value: best.toFixed(0),
    verdict: tone === "ok" ? "Sharp" : tone === "warn" ? "Borderline" : "Soft",
    tone,
  };
}

function clipCell(label: string, value: number | null, warnAt: number, badAt: number, badWord: string): Cell {
  if (value == null) return { label, value: "—", verdict: "", tone: "neutral" };
  const tone: Tone = value > badAt ? "bad" : value > warnAt ? "warn" : "ok";
  return {
    label,
    value: percent(value, value >= 10 ? 0 : 1),
    verdict: tone === "bad" ? badWord : tone === "warn" ? "Some" : "Clean",
    tone,
  };
}

/** The four measurements that decide whether the next frame needs to change. */
export function VerdictStrip({ photo, className }: { photo: PhotoDetail; className?: string }) {
  const a = photo.analysis;

  if (!a) {
    return (
      <p className={cn("text-ink-300 py-2 text-sm", className)} data-testid="verdict-strip">
        {photo.processing_status === "error"
          ? "Analysis unavailable for this frame."
          : "Measuring sharpness and exposure…"}
      </p>
    );
  }

  const cells: Cell[] = [
    {
      label: "Sharpness",
      value: a.sharpness_score?.toFixed(0) ?? "—",
      verdict: a.sharpness_label ?? "",
      tone: sharpnessTone(a.sharpness_score),
    },
    eyeCell(photo),
    clipCell("Highlights", a.highlight_clipping_percent, 0.5, 2, "Clipped"),
    clipCell("Shadows", a.shadow_clipping_percent, 1, 4, "Crushed"),
  ];

  return (
    <dl
      className={cn("divide-ink-800 grid grid-cols-4 divide-x", className)}
      data-testid="verdict-strip"
      aria-label="Frame check"
    >
      {cells.map((c) => (
        <div key={c.label} className="min-w-0 px-2 first:pl-0 last:pr-0">
          <dt className="text-ink-300 truncate text-xs">{c.label}</dt>
          <dd className={cn("mt-0.5 font-mono text-2xl leading-tight font-semibold", TONE_TEXT[c.tone])}>
            {c.value}
          </dd>
          <dd className={cn("truncate text-xs", TONE_TEXT[c.tone])}>{c.verdict || "\u00a0"}</dd>
        </div>
      ))}
    </dl>
  );
}
