import { AlertTriangle, Eye, ScanFace } from "lucide-react";
import { formatDateTime, percent, titleCase } from "@/lib/format";
import type { Analysis } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Histogram } from "./histogram";

export function sharpnessTone(score: number | null | undefined): "ok" | "warn" | "bad" | "neutral" {
  if (score == null) return "neutral";
  if (score >= 55) return "ok";
  if (score >= 35) return "warn";
  return "bad";
}

const TONE_BG = { ok: "bg-ok", warn: "bg-warn", bad: "bg-bad", neutral: "bg-ink-600" } as const;

function Meter({
  label,
  value,
  max = 100,
  display,
  tone = "neutral",
}: {
  label: string;
  value: number | null | undefined;
  max?: number;
  display?: string;
  tone?: keyof typeof TONE_BG;
}) {
  const pct = value == null ? 0 : Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-[12px]">
        <span className="text-ink-400">{label}</span>
        <span className="text-ink-100 tabular">{display ?? (value == null ? "—" : value.toFixed(0))}</span>
      </div>
      <div className="bg-ink-800 h-1.5 overflow-hidden rounded-full">
        <div
          className={cn("h-full rounded-full transition-all", TONE_BG[tone])}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function AnalysisPanel({ analysis }: { analysis: Analysis | null }) {
  if (!analysis) {
    return (
      <p className="text-ink-400 text-sm">Not analyzed yet. Analysis runs automatically after import.</p>
    );
  }
  const hi = analysis.highlight_clipping_percent ?? 0;
  const lo = analysis.shadow_clipping_percent ?? 0;
  const summary = [
    !analysis.exposure_assessment &&
      analysis.exposure_label &&
      `${titleCase(analysis.exposure_label)} exposure`,
    analysis.dynamic_range_ev != null && `~${analysis.dynamic_range_ev.toFixed(1)} EV tonal range`,
  ].filter(Boolean);

  return (
    <div className="space-y-4" data-testid="analysis-panel">
      {summary.length > 0 && <p className="text-ink-300 tabular text-sm">{summary.join(" · ")}</p>}

      <Histogram histogram={analysis.histogram} />

      {analysis.exposure_assessment && (
        <p className="text-ink-300 text-[13px]">{analysis.exposure_assessment}</p>
      )}

      <div className="grid grid-cols-2 gap-x-5 gap-y-3">
        <Meter
          label="Highlights clipped"
          value={hi}
          max={10}
          display={percent(hi, 2)}
          tone={hi > 2 ? "bad" : hi > 0.5 ? "warn" : "ok"}
        />
        <Meter
          label="Shadows clipped"
          value={lo}
          max={10}
          display={percent(lo, 2)}
          tone={lo > 4 ? "bad" : lo > 1 ? "warn" : "ok"}
        />
        <Meter
          label="Brightness"
          value={analysis.brightness != null ? analysis.brightness * 100 : null}
          display={analysis.brightness != null ? `${(analysis.brightness * 100).toFixed(0)}%` : undefined}
        />
        <Meter
          label="Contrast"
          value={analysis.contrast != null ? analysis.contrast * 100 : null}
          max={50}
          display={analysis.contrast != null ? `${(analysis.contrast * 100).toFixed(0)}%` : undefined}
        />
        <Meter
          label="Saturation"
          value={analysis.saturation != null ? analysis.saturation * 100 : null}
          display={analysis.saturation != null ? `${(analysis.saturation * 100).toFixed(0)}%` : undefined}
        />
        <Meter
          label="Peak detail"
          value={analysis.sharpness_peak}
          max={1500}
          display={analysis.sharpness_peak?.toFixed(0)}
        />
      </div>

      {analysis.dominant_colors.length > 0 && (
        <div>
          <div className="text-ink-400 mb-1.5 text-xs font-medium">Dominant colors</div>
          <div className="ring-ink-800 flex h-6 overflow-hidden rounded-md ring-1">
            {analysis.dominant_colors.map((c) => (
              <div
                key={c.hex}
                title={`${c.hex} · ${(c.fraction * 100).toFixed(0)}%`}
                style={{ background: c.hex, flexGrow: c.fraction }}
              />
            ))}
          </div>
        </div>
      )}

      <div className="text-ink-300 flex flex-wrap gap-x-5 gap-y-1 text-[12px]">
        <span className="flex items-center gap-1.5">
          <ScanFace className="text-ink-400 size-3.5" />
          {analysis.face_count == null
            ? "Face detection unavailable"
            : `${analysis.face_count} face(s) detected`}
        </span>
        {analysis.eye_count != null && analysis.eye_count > 0 && (
          <span className="flex items-center gap-1.5">
            <Eye className="text-ink-400 size-3.5" /> {analysis.eye_count} eye(s)
            {analysis.faces.some((f) => f.eyes.some((e) => e.sharpness != null)) && (
              <>
                {" "}
                · best eye sharpness{" "}
                {Math.max(...analysis.faces.flatMap((f) => f.eyes.map((e) => e.sharpness ?? 0))).toFixed(0)}
              </>
            )}
          </span>
        )}
      </div>

      {analysis.warnings.length > 0 && (
        <ul className="space-y-1.5">
          {analysis.warnings.map((w) => (
            <li key={w} className="bg-warn/5 text-warn/90 flex gap-2 rounded-md px-2.5 py-1.5 text-[12px]">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
              {w}
            </li>
          ))}
        </ul>
      )}

      <p className="text-ink-400 text-xs">
        Heuristic estimates from the {analysis.source ?? "preview"} · v{analysis.algorithm_version} ·{" "}
        {formatDateTime(analysis.analyzed_at)}
        {analysis.duration_ms != null && ` · ${analysis.duration_ms} ms`}
      </p>
    </div>
  );
}
