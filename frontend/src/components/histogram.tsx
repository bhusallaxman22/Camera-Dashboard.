import { useMemo } from "react";
import type { Analysis } from "@/lib/types";
import { cn } from "@/lib/utils";

const W = 256;
const H = 100;

function toPath(bins: number[], scale: number): string {
  let d = `M0 ${H}`;
  for (let i = 0; i < bins.length; i++) {
    const y = H - Math.min(1, (bins[i] ?? 0) / scale) * H;
    d += ` L${i} ${y.toFixed(2)}`;
  }
  return `${d} L${W - 1} ${H} Z`;
}

/**
 * RGB + luminance histogram. Uses a square-root scale with a high-percentile
 * ceiling so a single spike (e.g. a black border) doesn't flatten everything.
 */
export function Histogram({
  histogram,
  className,
  showClipping = true,
}: {
  histogram: Analysis["histogram"];
  className?: string;
  showClipping?: boolean;
}) {
  const paths = useMemo(() => {
    const channels = (["r", "g", "b", "l"] as const).filter((c) => histogram[c]?.length);
    if (!channels.length) return null;
    const all = channels
      .flatMap((c) => histogram[c] as number[])
      .map(Math.sqrt)
      .sort((a, b) => a - b);
    const scale = Math.max(1, all[Math.floor(all.length * 0.995)] ?? 1);
    const sqrt = (arr: number[]) => arr.map(Math.sqrt);
    return Object.fromEntries(channels.map((c) => [c, toPath(sqrt(histogram[c] as number[]), scale)]));
  }, [histogram]);

  if (!paths) {
    return (
      <div className={cn("text-ink-300 grid h-24 place-items-center text-xs", className)}>No histogram</div>
    );
  }

  const l = histogram.l ?? [];
  const total = l.reduce((a, b) => a + b, 0) || 1;
  const lowClip = ((l[0] ?? 0) / total) * 100;
  const highClip = ((l[255] ?? 0) / total) * 100;

  return (
    <div className={cn("relative", className)} data-testid="histogram">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="bg-ink-950 h-24 w-full rounded">
        {paths.l && <path d={paths.l} fill="#d4d4d8" fillOpacity={0.18} />}
        <g style={{ mixBlendMode: "screen" }}>
          {paths.r && <path d={paths.r} fill="#ef4444" fillOpacity={0.55} />}
          {paths.g && <path d={paths.g} fill="#22c55e" fillOpacity={0.55} />}
          {paths.b && <path d={paths.b} fill="#3b82f6" fillOpacity={0.55} />}
        </g>
        {[64, 128, 192].map((x) => (
          <line key={x} x1={x} x2={x} y1={0} y2={H} stroke="#ffffff" strokeOpacity={0.05} />
        ))}
      </svg>
      {showClipping && (
        <>
          <span
            className={cn(
              "absolute top-1 left-1 size-2 rounded-full",
              lowClip > 0.5 ? "bg-info shadow-info shadow-[0_0_6px]" : "bg-ink-700",
            )}
            title={`Shadows at 0: ${lowClip.toFixed(2)}%`}
          />
          <span
            className={cn(
              "absolute top-1 right-1 size-2 rounded-full",
              highClip > 0.5 ? "bg-bad shadow-bad shadow-[0_0_6px]" : "bg-ink-700",
            )}
            title={`Highlights at 255: ${highClip.toFixed(2)}%`}
          />
        </>
      )}
    </div>
  );
}
