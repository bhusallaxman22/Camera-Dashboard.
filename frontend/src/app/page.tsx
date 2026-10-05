"use client";

import { Activity, ArrowRight, Camera, Files, HardDrive, ImageIcon, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { ActivityFeed } from "@/components/activity-feed";
import { AnalysisPanel } from "@/components/analysis-panel";
import { CameraStatusCard } from "@/components/camera-status";
import { CritiquePanel } from "@/components/critique-panel";
import { CullingControls } from "@/components/culling-controls";
import { ExposureStrip } from "@/components/metadata-grid";
import { PhotoActions } from "@/components/photo-actions";
import { FileKindBadges, PhotoThumb } from "@/components/photo-thumb";
import { StatTile } from "@/components/stat-tile";
import { useToast } from "@/components/ui/toast";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatBytes, formatDateTime } from "@/lib/format";
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
          className="checker bg-ink-950 relative grid min-h-72 place-items-center xl:min-h-[30rem]"
        >
          {photo.preview_url ? (
            <img
              key={photo.preview_url}
              src={photo.preview_url}
              alt={photo.base_filename}
              className="animate-fade-in max-h-[70vh] w-full object-contain"
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
            <div className="flex items-center justify-between gap-2">
              <Link href={`/photos/${photo.id}`} className="hover:text-accent font-mono text-lg">
                {photo.base_filename}
              </Link>
              <span className="text-ink-400 text-xs">{formatDateTime(photo.capture_time)}</span>
            </div>
            <p className="text-ink-400 truncate text-sm">
              {[photo.camera, photo.lens_model].filter(Boolean).join(" · ") || "Unknown camera"}
            </p>
          </div>
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
    <div className="mx-auto max-w-[1600px] space-y-5 p-4 md:p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Studio</h1>
          <p className="text-ink-400 text-sm">
            Live ingest from your Z6III, paired, analyzed and ready to cull.
          </p>
        </div>
        <Link href="/library" className="text-ink-300 hover:text-accent flex items-center gap-1 text-sm">
          Open library <ArrowRight className="size-4" />
        </Link>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,1.3fr)_repeat(4,minmax(0,1fr))]">
        <CameraStatusCard status={s?.camera} />
        <StatTile
          label="Today"
          icon={<Camera className="size-3.5" />}
          value={s ? s.today.photos : "—"}
          hint={s ? `${s.today.picks} picks · ${s.today.rejects} rejects` : undefined}
        />
        <StatTile
          label="Files today"
          icon={<Files className="size-3.5" />}
          value={s ? s.today.raw_files + s.today.jpeg_files + s.today.videos : "—"}
          hint={
            s ? `${s.today.raw_files} RAW · ${s.today.jpeg_files} JPEG · ${s.today.videos} video` : undefined
          }
        />
        <StatTile
          label="Library"
          icon={<ImageIcon className="size-3.5" />}
          value={s ? s.totals.photos.toLocaleString() : "—"}
          hint={s ? `${s.totals.favorites} favorites · ${s.totals.rejected} rejected` : undefined}
        />
        <StatTile
          label="Storage"
          icon={<HardDrive className="size-3.5" />}
          value={s ? formatBytes(s.totals.bytes) : "—"}
          hint={
            s && (s.totals.pending > 0 || s.totals.errors > 0)
              ? `${s.totals.pending} processing · ${s.totals.errors} errors`
              : s
                ? `${formatBytes(s.today.bytes)} today`
                : undefined
          }
        />
      </div>

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
