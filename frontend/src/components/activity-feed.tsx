"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatRelative } from "@/lib/format";
import { useNow } from "@/lib/hooks";
import { cn } from "@/lib/utils";

const LEVEL_DOT: Record<string, string> = {
  info: "bg-ink-500",
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
  if (isLoading) return <p className="text-ink-500 text-sm">Loading…</p>;
  if (!data?.length) return <p className="text-ink-500 text-sm">No activity yet.</p>;
  return (
    <ol className={cn("space-y-2", className)} data-testid="activity-feed">
      {data.map((e) => (
        <li key={e.id} className="flex gap-2.5 text-[13px]">
          <span className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", LEVEL_DOT[e.level] ?? "bg-ink-500")} />
          <div className="min-w-0 flex-1">
            <div className="text-ink-200 truncate">
              {e.photo_id ? (
                <Link href={`/photos/${e.photo_id}`} className="hover:text-accent">
                  {e.message}
                </Link>
              ) : (
                e.message
              )}
            </div>
            <div className="text-ink-500 text-[11px]">
              <span className="font-mono">{e.category}</span> · {formatRelative(e.created_at, now)}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}
