import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Tone = "neutral" | "ok" | "warn" | "bad" | "info" | "accent";

const TONES: Record<Tone, string> = {
  neutral: "bg-ink-800 text-ink-300 ring-ink-700",
  ok: "bg-ok/10 text-ok ring-ok/25",
  warn: "bg-warn/10 text-warn ring-warn/25",
  bad: "bg-bad/10 text-bad ring-bad/25",
  info: "bg-info/10 text-info ring-info/25",
  accent: "bg-accent-soft text-accent ring-accent/30",
};

export function Badge({
  className,
  tone = "neutral",
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-semibold ring-1 ring-inset",
        TONES[tone],
        className,
      )}
      {...props}
    />
  );
}
