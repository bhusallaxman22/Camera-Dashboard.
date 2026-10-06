"use client";

import { AlertTriangle, ArrowRight } from "lucide-react";
import Link from "next/link";
import { formatBytes, formatRelative } from "@/lib/format";
import { useNow } from "@/lib/hooks";
import type { Stats } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Skeleton } from "./ui/skeleton";

const STATE_LABEL = { receiving: "Receiving", idle: "Idle", never: "Waiting for first upload" } as const;

function plural(n: number, word: string) {
  return `${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`;
}

/** One line of shoot context, so the latest frame can own the screen. */
export function CameraStatusBar({ stats }: { stats: Stats | undefined }) {
  const now = useNow(5_000);
  if (!stats) return <Skeleton className="h-12 w-full rounded-xl max-md:hidden" />;

  const { camera, today, totals } = stats;
  const receiving = camera.state === "receiving";
  const backlog = totals.pending > 0 || totals.errors > 0;

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-x-5 gap-y-1.5 rounded-xl border px-4 py-2.5 text-sm",
        receiving ? "border-ok/30 bg-ok/[0.04]" : "border-ink-800 bg-ink-900/80",
        // Phones carry camera state in the header; the card only earns space when work is stuck.
        !backlog && "max-md:hidden",
      )}
      data-testid="camera-status"
    >
      <span className="flex min-w-0 items-center gap-2">
        <span
          className={cn("size-2 shrink-0 rounded-full", receiving ? "pulse-ring bg-ok" : "bg-ink-400")}
          aria-hidden
        />
        <span className="truncate font-semibold">{camera.camera ?? "Nikon Z6III"}</span>
        <span className={receiving ? "text-ok" : "text-ink-300"}>{STATE_LABEL[camera.state]}</span>
        {camera.last_upload_at && (
          <span className="text-ink-300 tabular">· {formatRelative(camera.last_upload_at, now)}</span>
        )}
      </span>

      {camera.session_photos > 0 && (
        <span className="text-ink-300 tabular">
          Session <span className="text-ink-100">{plural(camera.session_photos, "photo")}</span> ·{" "}
          {formatBytes(camera.session_bytes)}
        </span>
      )}

      {today.photos > 0 && (
        <span className="text-ink-300 tabular">
          Today <span className="text-ink-100">{today.photos.toLocaleString()}</span> ·{" "}
          {plural(today.picks, "pick")} · {plural(today.rejects, "reject")}
        </span>
      )}

      {backlog && (
        <Link
          href="/system"
          className="text-warn hover:text-ink-100 tabular flex items-center gap-1.5"
          title="Open System to see queues and failed jobs"
        >
          <AlertTriangle className="size-3.5" />
          {[
            totals.pending > 0 && `${totals.pending.toLocaleString()} processing`,
            totals.errors > 0 && plural(totals.errors, "error"),
          ]
            .filter(Boolean)
            .join(" · ")}
        </Link>
      )}

      <Link
        href="/library"
        className="text-ink-300 hover:text-accent tabular -my-2 ml-auto flex items-center gap-1 py-2"
      >
        Library <span className="text-ink-100">{totals.photos.toLocaleString()}</span>
        <ArrowRight className="size-3.5" />
      </Link>
    </div>
  );
}
