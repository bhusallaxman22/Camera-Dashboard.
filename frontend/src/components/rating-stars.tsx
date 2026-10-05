"use client";

import { Star } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  value: number;
  onChange?: (value: number) => void;
  size?: "sm" | "md";
  className?: string;
}

/** 0–5 stars. Clicking the current rating clears it (Lightroom behaviour). */
export function RatingStars({ value, onChange, size = "md", className }: Props) {
  const icon = size === "sm" ? "size-3" : "size-4.5";
  if (!onChange) {
    return (
      <span className={cn("inline-flex gap-0.5", className)} aria-label={`${value} of 5 stars`}>
        {[1, 2, 3, 4, 5].map((n) => (
          <Star key={n} className={cn(icon, n <= value ? "fill-accent text-accent" : "text-ink-600")} />
        ))}
      </span>
    );
  }
  return (
    <div role="radiogroup" aria-label="Rating" className={cn("inline-flex gap-0.5", className)}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={value === n}
          aria-label={`${n} star${n > 1 ? "s" : ""}`}
          onClick={() => onChange(value === n ? 0 : n)}
          className="rounded p-0.5 transition-transform hover:scale-110"
        >
          <Star
            className={cn(icon, n <= value ? "fill-accent text-accent" : "text-ink-500 hover:text-ink-300")}
          />
        </button>
      ))}
    </div>
  );
}
