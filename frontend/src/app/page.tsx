"use client";

import { Activity, Camera, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { ActivityFeed } from "@/components/activity-feed";
import { AnalysisPanel } from "@/components/analysis-panel";
import { CameraStatusBar } from "@/components/camera-status";
import { CritiquePanel } from "@/components/critique-panel";
import { CullingControls } from "@/components/culling-controls";
import { ExposureStrip } from "@/components/metadata-grid";
import { PhotoActions } from "@/components/photo-actions";
import { FileKindBadges, PhotoThumb } from "@/components/photo-thumb";
import { VerdictStrip } from "@/components/verdict-strip";
import { useToast } from "@/components/ui/toast";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatBytes, formatDateTime, formatTime } from "@/lib/format";
import { usePhoto, usePhotoUpdate, useStats } from "@/lib/hooks";
import { useLiveListener } from "@/lib/live";
import type { PhotoDetail } from "@/lib/types";
import { cn } from "@/lib/utils";

function LatestPhoto({ photo }: { photo: PhotoDetail }) {
  const update = usePhotoUpdate(photo.id);
  return (
    <Card className="overflow-hidden" data-testid="latest-photo">
      <div className="grid gap-0 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Link
          href={`/photos/${photo.id}`}
          className="checker bg-ink-950 relative grid min-h-56 place-items-center sm:min-h-72 xl:min-h-[30rem] xl:self-start"
        >
          {photo.preview_url ? (
            <img
              key={photo.preview_url}
              src={photo.preview_url}
              alt={photo.base_filename}
              className="animate-fade-in max-h-[58vh] w-full object-contain sm:max-h-[70vh]"
            />
          ) : (
            <span className="text-ink-500 text-sm">
              {photo.processing_status === "error" ? "Preview failed" : "Generating preview…"}
            </span>
          )}
          <span className="absolute top-3 left-3 flex items-center gap-2">
            <Badge tone="accent">Latest</Badge>
            <FileKindBadges photo={photo} />
          </span>
        </Link>

        <div className="border-ink-800 flex flex-col gap-4 border-t p-4 xl:border-t-0 xl:border-l">
          <div>
            <div className="flex items-baseline justify-between gap-2">
              <Link href={`/photos/${photo.id}`} className="hover:text-accent font-mono text-lg">
                {photo.base_filename}
              </Link>
              <time
                dateTime={photo.capture_time ?? undefined}
                title={formatDateTime(photo.capture_time)}
                className="text-ink-300 tabular text-xs"
              >
                {formatTime(photo.capture_time)}
              </time>
            </div>
            <p className="text-ink-300 truncate text-sm">
              {[photo.camera, photo.lens_model].filter(Boolean).join(" · ") || "Unknown camera"}
            </p>
          </div>
          <VerdictStrip photo={photo} />
          <ExposureStrip photo={photo} />
          <CullingControls photo={photo} onUpdate={(b) => update.mutate(b)} />

          <div className="space-y-1 text-[12px]">
            {photo.files
              .filter((f) => !f.is_duplicate)
              .map((f) => (
                <div key={f.id} className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-1.5">
                    <span className={cn("size-1.5 rounded-full", f.exists ? "bg-ok" : "bg-bad")} />
                    <span className="text-ink-200 font-mono">{f.filename}</span>
                  </span>
                  <span className="text-ink-400 tabular">{formatBytes(f.file_size)}</span>
                </div>
              ))}
            {!photo.has_raw && photo.media_type === "still" && (
              <div className="text-ink-500">No RAW paired (yet)</div>
            )}
          </div>

          <PhotoActions photo={photo} compact />

          <div className="border-ink-800 border-t pt-3">
            <AnalysisSummary photo={photo} />
          </div>
        </div>
      </div>
    </Card>
  );
}

function AnalysisSummary({ photo }: { photo: PhotoDetail }) {
  const [tab, setTab] = useState<"analysis" | "ai">("analysis");
  return (
    <div>
      <div className="mb-3 flex gap-1">
        {(["analysis", "ai"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "rounded px-2 py-1 text-[11px] font-semibold tracking-wider uppercase",
              tab === t ? "bg-ink-800 text-ink-100" : "text-ink-500 hover:text-ink-300",
            )}
          >
            {t === "analysis" ? "Technical" : "AI feedback"}
          </button>
        ))}
      </div>
      {tab === "analysis" ? (
        <AnalysisPanel analysis={photo.analysis} />
      ) : (
        <CritiquePanel critique={photo.critique} history={photo.critique_history} />
      )}
    </div>
  );
}

export default function DashboardPage() {
  const toast = useToast();
  const stats = useStats();
  const latest = usePhoto(stats.data?.latest_photo_id);

  useLiveListener((msg) => {
    if (msg.type === "photo.created") {
      toast(`New photo: ${String(msg.data.filename ?? "")}`, "ok");
    }
  });

  const s = stats.data;
  return (
    <div className="mx-auto max-w-[1600px] space-y-4 p-3 sm:p-4 md:space-y-5 md:p-6">
      <h1 className="sr-only">Dashboard</h1>
      <CameraStatusBar stats={s} />

      {latest.data ? (
        <LatestPhoto photo={latest.data} />
      ) : stats.isLoading || latest.isLoading ? (
        <Skeleton className="h-[30rem] w-full rounded-xl" />
      ) : (
        <Card className="grid h-72 place-items-center text-center">
          <div>
            <Camera className="text-ink-600 mx-auto mb-3 size-8" />
            <p className="text-ink-300">No photos yet</p>
            <p className="text-ink-500 text-sm">
              Shoot with FTP upload enabled — new frames appear here within seconds.
            </p>
          </div>
        </Card>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card>
          <CardHeader
            title="Recent"
            icon={<Sparkles className="size-3.5" />}
            action={
              <Link href="/library" className="text-ink-400 hover:text-accent text-xs">
                View all
              </Link>
            }
          />
          <CardBody>
            {s?.recent.length ? (
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">
                {s.recent.map((p) => (
                  <PhotoThumb key={p.id} photo={p} />
                ))}
              </div>
            ) : stats.isLoading ? (
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">
                {Array.from({ length: 4 }, (_, i) => (
                  <Skeleton key={i} className="aspect-[3/2] w-full" />
                ))}
              </div>
            ) : (
              <p className="text-ink-500 text-sm">Nothing imported yet.</p>
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Activity" icon={<Activity className="size-3.5" />} />
          <CardBody>
            <ActivityFeed limit={14} />
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
