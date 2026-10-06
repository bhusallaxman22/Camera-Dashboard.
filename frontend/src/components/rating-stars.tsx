"use client";

import { Star } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  value: number;
  onChange?: (value: number) => void;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const HIT = {
  sm: "size-8",
  md: "size-9 pointer-coarse:size-11",
  lg: "size-11",
} as const;

/** 0–5 stars. Clicking the current rating clears it (Lightroom behaviour). */
export function RatingStars({ value, onChange, size = "md", className }: Props) {
  if (!onChange) {
    const icon = size === "sm" ? "size-3" : "size-4.5";
    return (
      <span className={cn("inline-flex gap-0.5", className)} aria-label={`${value} of 5 stars`}>
        {[1, 2, 3, 4, 5].map((n) => (
          <Star key={n} className={cn(icon, n <= value ? "fill-accent text-accent" : "text-ink-600")} />
        ))}
      </span>
    );
  }
  const icon = size === "lg" ? "size-6" : "size-5";
  return (
    <div role="radiogroup" aria-label="Rating" className={cn("inline-flex", className)}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={value === n}
          aria-label={`${n} star${n > 1 ? "s" : ""}`}
          title={`${n} star${n > 1 ? "s" : ""} (${n})`}
          onClick={() => onChange(value === n ? 0 : n)}
          className={cn(
            "group grid place-items-center rounded-md transition-transform active:scale-90",
            HIT[size],
          )}
        >
          <Star
            className={cn(
              icon,
              n <= value ? "fill-accent text-accent" : "text-ink-400 group-hover:text-ink-200",
            )}
          />
        </button>
      ))}
    </div>
  );
}
