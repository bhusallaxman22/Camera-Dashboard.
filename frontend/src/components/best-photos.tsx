"use client";

import { Check, ChevronLeft, ChevronRight, Heart, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { formatTime } from "@/lib/format";
import { useBestPhotos } from "@/lib/hooks";
import type { BestPeriod, BestPhoto } from "@/lib/types";
import { cn } from "@/lib/utils";
import { sharpnessTone } from "./analysis-panel";
import { Button } from "./ui/button";
import { Skeleton } from "./ui/skeleton";

const PERIODS: [BestPeriod, string][] = [
  ["session", "Session"],
  ["today", "Today"],
  ["7d", "7 days"],
  ["all", "All time"],
];

const IN_PERIOD: Record<BestPeriod, string> = {
  session: "this session",
  today: "today",
  "7d": "the last 7 days",
  all: "the library",
};

const TONE_TEXT = { ok: "text-ok", warn: "text-warn", bad: "text-bad", neutral: "text-ink-200" } as const;

// Same cut-offs as the verdict strip's eye cell.
function eyeTone(v: number) {
  return v >= 45 ? "ok" : v >= 30 ? "warn" : "bad";
}

function Factor({ label, value, tone }: { label: string; value: string; tone: keyof typeof TONE_TEXT }) {
  return (
    <span className="flex items-baseline gap-1">
      <span className="text-ink-300 text-xs">{label}</span>
      <span className={cn("font-mono text-base font-semibold", TONE_TEXT[tone])}>{value}</span>
    </span>
  );
}

function BestCard({ item, rank }: { item: BestPhoto; rank: number }) {
  const p = item.photo;
  const portrait = Boolean(p.thumb_width && p.thumb_height && p.thumb_height > p.thumb_width);
  const ai = item.aesthetic_score;
  return (
    <Link
      href={`/photos/${p.id}`}
      className="group bg-ink-850 ring-ink-800 hover:ring-ink-500 block overflow-hidden rounded-xl ring-1 transition"
      data-testid="best-card"
    >
      <div className={cn("relative aspect-[3/2] overflow-hidden", portrait && "bg-ink-950")}>
        {p.thumb_url ? (
          <img
            src={p.thumb_url}
            alt={p.base_filename}
            loading="lazy"
            decoding="async"
            draggable={false}
            className={cn(
              "absolute inset-0 size-full transition-transform duration-300 group-hover:scale-[1.02]",
              portrait ? "object-contain" : "object-cover",
            )}
          />
        ) : (
          <div className="text-ink-300 absolute inset-0 grid place-items-center text-sm">No preview</div>
        )}
        <span className="bg-ink-950/85 text-ink-100 tabular absolute top-2 left-2 rounded-md px-2 py-0.5 text-sm font-semibold">
          #{rank}
        </span>
        <span className="absolute top-2 right-2 flex items-center gap-1">
          {p.picked && (
            <span className="bg-ok text-ink-950 grid size-6 place-items-center rounded-full" title="Pick">
              <Check className="size-3.5" strokeWidth={3} />
            </span>
          )}
          {p.favorite && (
            <Heart className="fill-accent text-accent size-5 drop-shadow" aria-label="Favorite" />
          )}
        </span>
      </div>
      <div className="space-y-1 px-3 py-2.5">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
          <span
            className={cn(
              "rounded-md px-1.5 py-0.5 font-mono text-sm font-semibold",
              ai != null ? "bg-accent-soft text-accent" : "bg-ink-800 text-ink-300",
            )}
            title={
              ai != null ? "AI aesthetic estimate (0–10)" : "No AI score yet; ranked on sharpness and eyes"
            }
          >
            {ai != null ? `AI ${ai.toFixed(1)}` : "No AI"}
          </span>
          {p.sharpness_score != null && (
            <Factor
              label="Sharp"
              value={p.sharpness_score.toFixed(0)}
              tone={sharpnessTone(p.sharpness_score)}
            />
          )}
          {item.eye_sharpness != null && (
            <Factor label="Eyes" value={item.eye_sharpness.toFixed(0)} tone={eyeTone(item.eye_sharpness)} />
          )}
        </div>
        <div className="text-ink-300 flex items-center justify-between gap-2 text-xs">
          <span className="text-ink-200 truncate font-mono">{p.base_filename}</span>
          <span className="tabular shrink-0">{formatTime(p.capture_time)}</span>
        </div>
      </div>
    </Link>
  );
}

/**
 * Strongest frames for a period, ranked server-side from the AI aesthetic estimate
 * blended with measured sharpness and eye focus; one frame per burst, no rejects.
 */
export function BestPhotos({ receiving, shotToday }: { receiving: boolean; shotToday: boolean }) {
  const [chosen, setChosen] = useState<BestPeriod | null>(null);
  // While shooting, or on a day with no frames yet, the latest session is the useful default.
  const period = chosen ?? (shotToday && !receiving ? "today" : "session");
  const best = useBestPhotos(period);
  const rail = useRef<HTMLUListElement>(null);
  const data = best.data;
  const items = data?.items ?? [];
  const shown = data?.period ?? period;

  const scroll = (dir: 1 | -1) => {
    const el = rail.current;
    if (el) el.scrollBy({ left: dir * el.clientWidth * 0.8, behavior: "smooth" });
  };

  let note: string | null = null;
  if (data && data.candidates > 0) {
    const n = data.candidates.toLocaleString();
    note =
      data.ai_scored === 0
        ? `No AI scores in ${IN_PERIOD[shown]} yet, so these ${n} frames are ranked on sharpness and eye focus only.`
        : data.ai_scored < data.candidates
          ? `${data.ai_scored.toLocaleString()} of ${n} frames have an AI score; the rest are ranked on sharpness and eye focus. Best frame per burst, rejects left out.`
          : `Ranked from ${n} frames by AI aesthetic, sharpness and eye focus. Best frame per burst, rejects left out.`;
  }

  return (
    <section
      aria-labelledby="best-heading"
      className="border-ink-800 bg-ink-900/80 rounded-xl border py-3.5"
      data-testid="best-photos"
    >
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4">
        <h2 id="best-heading" className="flex items-center gap-2 text-base font-semibold">
          <Sparkles className="text-accent size-4" /> Best shots
        </h2>
        <div
          role="group"
          aria-label="Period"
          className="bg-ink-850 ring-ink-800 flex rounded-lg p-0.5 ring-1"
        >
          {PERIODS.map(([key, label]) => (
            <button
              key={key}
              type="button"
              aria-pressed={period === key}
              onClick={() => setChosen(key)}
              className={cn(
                "h-9 rounded-md px-3 text-sm font-medium transition-colors pointer-coarse:h-11",
                period === key ? "bg-ink-700 text-ink-100" : "text-ink-300 hover:text-ink-100",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      {note && <p className="text-ink-300 mt-2 px-4 text-sm">{note}</p>}

      <div className="relative mt-3">
        {best.isError ? (
          <p className="text-bad px-4 text-sm">Could not rank photos: {best.error.message}</p>
        ) : !data ? (
          <ul className="flex scrollbar-none gap-3 overflow-hidden px-4">
            {Array.from({ length: 4 }, (_, i) => (
              <li key={i} className="w-[80%] shrink-0 sm:w-64">
                <Skeleton className="aspect-[5/4] w-full rounded-xl" />
              </li>
            ))}
          </ul>
        ) : items.length === 0 ? (
          <div className="border-ink-700 mx-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed px-4 py-6">
            <p className="text-ink-200 text-sm">
              {shown === "session" && !data.period_start
                ? "No shooting session yet. A session starts with the first upload after a 20-minute break."
                : `No analysed frames in ${IN_PERIOD[shown]} yet.`}
            </p>
            {shown !== "all" && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setChosen(shown === "session" ? "today" : "all")}
              >
                Show {shown === "session" ? "today" : "all time"}
              </Button>
            )}
          </div>
        ) : (
          <>
            <ul
              ref={rail}
              className={cn(
                "flex snap-x snap-mandatory scroll-px-4 scrollbar-none gap-3 overflow-x-auto px-4 pb-1 transition-opacity",
                best.isPlaceholderData && "opacity-60",
              )}
            >
              {items.map((item, i) => (
                <li key={item.photo.id} className="w-[80%] shrink-0 snap-start sm:w-64">
                  <BestCard item={item} rank={i + 1} />
                </li>
              ))}
            </ul>
            {items.length > 3 && (
              <div className="pointer-events-none absolute inset-y-0 right-2 left-2 hidden items-center justify-between md:flex pointer-coarse:hidden">
                <Button
                  size="icon"
                  variant="default"
                  onClick={() => scroll(-1)}
                  aria-label="Scroll best shots left"
                  className="bg-ink-950/85 pointer-events-auto rounded-full shadow-lg"
                >
                  <ChevronLeft className="size-5" />
                </Button>
                <Button
                  size="icon"
                  variant="default"
                  onClick={() => scroll(1)}
                  aria-label="Scroll best shots right"
                  className="bg-ink-950/85 pointer-events-auto rounded-full shadow-lg"
                >
                  <ChevronRight className="size-5" />
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
