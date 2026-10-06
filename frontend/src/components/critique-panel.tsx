import { Lightbulb, Sparkles, TriangleAlert, Wrench } from "lucide-react";
import type { ReactNode } from "react";
import { formatDateTime, titleCase } from "@/lib/format";
import type { Critique } from "@/lib/types";
import { Badge } from "./ui/badge";

function List({ title, icon, items }: { title: string; icon: ReactNode; items: string[] }) {
  if (!items.length) return null;
  return (
    <div>
      <div className="text-ink-200 mb-1 flex items-center gap-1.5 text-sm font-semibold">
        {icon}
        {title}
      </div>
      <ul className="text-ink-200 space-y-1 text-[13px]">
        {items.map((s) => (
          <li key={s} className="flex gap-2">
            <span className="bg-ink-500 mt-2 size-1 shrink-0 rounded-full" />
            {s}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CritiquePanel({ critique, history }: { critique: Critique | null; history?: number }) {
  if (!critique) {
    return <p className="text-ink-400 text-sm">No AI feedback yet.</p>;
  }
  if (critique.status !== "succeeded") {
    return (
      <div className="bg-bad/10 text-bad rounded-md p-3 text-[13px]">
        {critique.provider} critique failed: {critique.error ?? "unknown error"}
      </div>
    );
  }
  return (
    <div className="space-y-3.5" data-testid="critique-panel">
      <div className="flex flex-wrap items-center gap-2">
        {critique.scene && <Badge tone="accent">{titleCase(critique.scene)}</Badge>}
        <Badge>
          {critique.provider}
          {critique.model_name ? ` · ${critique.model_name}` : ""}
        </Badge>
        {critique.confidence != null && <Badge>confidence {(critique.confidence * 100).toFixed(0)}%</Badge>}
        {critique.aesthetic_score != null && (
          <Badge tone="info">aesthetic {critique.aesthetic_score.toFixed(1)}/10</Badge>
        )}
      </div>
      {critique.subject && <p className="text-ink-300 text-[13px]">Subject: {critique.subject}</p>}
      {critique.description && (
        <p className="text-ink-100 text-[14px] leading-relaxed">{critique.description}</p>
      )}
      <List title="Composition" icon={<Sparkles className="size-3" />} items={critique.composition} />
      <List title="Technical" icon={<Wrench className="size-3" />} items={critique.technical} />
      <List title="Possible issues" icon={<TriangleAlert className="size-3" />} items={critique.issues} />
      <List title="Suggestions" icon={<Lightbulb className="size-3" />} items={critique.suggestions} />
      {critique.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {critique.tags.map((t) => (
            <span key={t} className="bg-ink-800 text-ink-300 rounded px-1.5 py-0.5 text-xs">
              #{t}
            </span>
          ))}
        </div>
      )}
      <p className="text-ink-400 text-xs">
        {formatDateTime(critique.created_at)}
        {critique.duration_ms != null && ` · ${critique.duration_ms} ms`}
        {history && history > 1 ? ` · ${history} critiques on record` : ""}
      </p>
    </div>
  );
}
