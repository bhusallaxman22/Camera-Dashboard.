"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatRelative } from "@/lib/format";
import { useNow } from "@/lib/hooks";
import { cn } from "@/lib/utils";

const LEVEL_DOT: Record<string, string> = {
  info: "bg-ink-400",
  warning: "bg-warn",
  error: "bg-bad",
};

export function ActivityFeed({ limit = 15, className }: { limit?: number; className?: string }) {
  const now = useNow();
  const { data, isLoading } = useQuery({
    queryKey: ["events", { limit }],
    queryFn: () => api.events({ limit }),
    refetchInterval: 60_000,
  });
  if (isLoading) return <p className="text-ink-400 text-sm">Loading…</p>;
  if (!data?.length) return <p className="text-ink-400 text-sm">No activity yet.</p>;
  return (
    <ol className={cn("-mx-2", className)} data-testid="activity-feed">
      {data.map((e) => {
        const body = (
          <>
            <span
              className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", LEVEL_DOT[e.level] ?? "bg-ink-400")}
            />
            <span className="min-w-0 flex-1">
              <span className="text-ink-200 block truncate">{e.message}</span>
              <span className="text-ink-400 block text-xs">
                <span className="font-mono">{e.category}</span> · {formatRelative(e.created_at, now)}
              </span>
            </span>
          </>
        );
        const row = "flex gap-2.5 rounded-md px-2 py-1.5 text-sm";
        return (
          <li key={e.id}>
            {e.photo_id ? (
              <Link href={`/photos/${e.photo_id}`} className={cn(row, "hover:bg-ink-850 active:bg-ink-800")}>
                {body}
              </Link>
            ) : (
              <div className={row}>{body}</div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
