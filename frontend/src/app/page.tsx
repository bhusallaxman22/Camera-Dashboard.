"use client";

import {
  Activity,
  ArrowUpToLine,
  Camera,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Images,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { ActivityFeed } from "@/components/activity-feed";
import { AnalysisPanel } from "@/components/analysis-panel";
import { BestPhotos } from "@/components/best-photos";
import { CameraStatusBar } from "@/components/camera-status";
import { CritiquePanel } from "@/components/critique-panel";
import { CullingControls } from "@/components/culling-controls";
import { ExposureStrip } from "@/components/metadata-grid";
import { PhotoActions } from "@/components/photo-actions";
import { FileKindBadges, PhotoThumb } from "@/components/photo-thumb";
import { CULL_SHORTCUTS, ShortcutLegend } from "@/components/shortcut-legend";
import { VerdictStrip } from "@/components/verdict-strip";
import { Badge } from "@/components/ui/badge";
import { Button, buttonClass } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime, formatTime } from "@/lib/format";
import { usePhoto, usePhotoUpdate, usePrefetchPhotos, useStats } from "@/lib/hooks";
import type { PhotoDetail, PhotoUpdate } from "@/lib/types";
import { useCullingKeys } from "@/lib/use-culling-keys";
import { useSwipe, type SwipeDir } from "@/lib/use-swipe";
import { cn } from "@/lib/utils";

const SHORTCUTS: [string, string][] = [
  ...CULL_SHORTCUTS,
  ["← / →", "Newer / older"],
  ["L", "Back to latest"],
];

interface Browse {
  /** Photo being shown; null follows the newest upload. */
  id: string | null;
  /** How many frames older than the newest the user has stepped. */
  back: number;
  /** Newest upload at the moment browsing started, to detect new arrivals. */
  from: string | null;
  enter: SwipeDir | null;
}

const FOLLOW: Browse = { id: null, back: 0, from: null, enter: null };

function FrameImage({
  photo,
  back,
  enter,
  dimmed,
  onNewer,
  onOlder,
}: {
  photo: PhotoDetail;
  back: number;
  enter: SwipeDir | null;
  dimmed: boolean;
  onNewer: (() => void) | null;
  onOlder: (() => void) | null;
}) {
  const swipe = useSwipe({
    onSwipe: (dir) => (dir === "left" ? onOlder?.() : onNewer?.()),
    canSwipe: (dir) => Boolean(dir === "left" ? onOlder : onNewer),
  });
  return (
    <div
      className="checker bg-ink-950 group relative grid min-h-56 place-items-center overflow-hidden sm:min-h-72"
      style={{ touchAction: "pan-y" }}
      {...swipe.handlers}
      data-testid="frame-image"
    >
      <Link
        href={`/photos/${photo.id}`}
        className="grid w-full place-items-center"
        aria-label={`Open ${photo.base_filename}`}
      >
        {photo.preview_url ? (
          <img
            key={photo.id}
            src={photo.preview_url}
            alt={photo.base_filename}
            draggable={false}
            className={cn(
              "max-h-[58svh] w-full object-contain transition-opacity sm:max-h-[70svh] xl:max-h-[max(34rem,calc(100svh-6.75rem))]",
              enter === "right"
                ? "animate-enter-right"
                : enter === "left"
                  ? "animate-enter-left"
                  : "animate-fade-in",
              dimmed && "opacity-70",
            )}
            style={
              swipe.dx
                ? {
                    transform: `translateX(${swipe.dx}px)`,
                    opacity: Math.max(0.55, 1 - Math.abs(swipe.dx) / 600),
                  }
                : undefined
            }
          />
        ) : (
          <span className="text-ink-300 py-24 text-sm">
            {photo.processing_status === "error" ? "Preview failed" : "Generating preview…"}
          </span>
        )}
      </Link>
      <span className="pointer-events-none absolute top-3 left-3 flex items-center gap-2">
        <Badge tone={back === 0 ? "accent" : "neutral"} className="bg-ink-950/85">
          {back === 0 ? "Latest" : `${back} back`}
        </Badge>
        <FileKindBadges photo={photo} />
      </span>
      {[
        { fn: onNewer, label: "Newer frame", side: "left-2", Icon: ChevronLeft },
        { fn: onOlder, label: "Older frame", side: "right-2", Icon: ChevronRight },
      ].map(({ fn, label, side, Icon }) => (
        <Button
          key={label}
          size="icon"
          variant="default"
          disabled={!fn}
          onClick={() => fn?.()}
          aria-label={label}
          title={`${label} (${side === "left-2" ? "←" : "→"})`}
          className={cn(
            "bg-ink-950/80 pointer-coarse:bg-ink-950/55 absolute top-1/2 size-11 -translate-y-1/2 rounded-full opacity-0 shadow-lg transition-opacity group-hover:opacity-100 focus-visible:opacity-100 disabled:hidden pointer-coarse:opacity-80",
            side,
          )}
        >
          <Icon className="size-5" />
        </Button>
      ))}
    </div>
  );
}

function AnalysisSummary({ photo }: { photo: PhotoDetail }) {
  const [tab, setTab] = useState<"analysis" | "ai">("analysis");
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls="dash-analysis"
        className="text-ink-200 hover:text-ink-100 flex h-11 w-full items-center justify-between text-sm font-medium xl:hidden"
      >
        {open ? "Hide analysis and AI feedback" : "Show analysis and AI feedback"}
        <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
      </button>
      <div id="dash-analysis" className={cn(!open && "max-xl:hidden", "max-xl:pt-2")}>
        <AnalysisTabs photo={photo} tab={tab} setTab={setTab} />
      </div>
    </div>
  );
}

function AnalysisTabs({
  photo,
  tab,
  setTab,
}: {
  photo: PhotoDetail;
  tab: "analysis" | "ai";
  setTab: (t: "analysis" | "ai") => void;
}) {
  return (
    <div>
      <div role="tablist" aria-label="Frame analysis" className="bg-ink-850 mb-3 flex rounded-lg p-0.5">
        {(["analysis", "ai"] as const).map((t) => (
          <button
            key={t}
            id={`dash-tab-${t}`}
            role="tab"
            aria-selected={tab === t}
            aria-controls="dash-analysis-panel"
            onClick={() => setTab(t)}
            className={cn(
              "h-9 flex-1 rounded-md text-sm font-medium transition-colors pointer-coarse:h-11",
              tab === t ? "bg-ink-700 text-ink-100" : "text-ink-300 hover:text-ink-100",
            )}
          >
            {t === "analysis" ? "Technical" : "AI feedback"}
          </button>
        ))}
      </div>
      <div id="dash-analysis-panel" role="tabpanel" aria-labelledby={`dash-tab-${tab}`}>
        {tab === "analysis" ? (
          <AnalysisPanel analysis={photo.analysis} />
        ) : (
          <CritiquePanel critique={photo.critique} history={photo.critique_history} />
        )}
      </div>
    </div>
  );
}

function FrameDetails({ photo, onUpdate }: { photo: PhotoDetail; onUpdate: (b: PhotoUpdate) => void }) {
  return (
    <div className="border-ink-800 flex flex-col gap-4 border-t p-4 xl:overflow-y-auto xl:overscroll-contain xl:border-t-0 xl:border-l">
      <div>
        <div className="flex items-baseline justify-between gap-2">
          <Link href={`/photos/${photo.id}`} className="hover:text-accent truncate font-mono text-lg">
            {photo.base_filename}
          </Link>
          <time
            dateTime={photo.capture_time ?? undefined}
            title={formatDateTime(photo.capture_time)}
            className="text-ink-300 tabular shrink-0 text-sm"
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
      <CullingControls
        photo={photo}
        onUpdate={onUpdate}
        extra={
          <>
            <PhotoActions photo={photo} compact className="contents" />
            <ShortcutLegend shortcuts={SHORTCUTS} />
          </>
        }
      />
      <div className="border-ink-800 border-t pt-3">
        <AnalysisSummary photo={photo} />
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const stats = useStats();
  const s = stats.data;
  const latestId = s?.latest_photo_id ?? null;
  const [browse, setBrowse] = useState<Browse>(FOLLOW);
  const shownId = browse.id ?? latestId;
  const frame = usePhoto(shownId, { keepPrevious: true });
  const photo = frame.data;
  const update = usePhotoUpdate(photo?.id ?? "");
  usePrefetchPhotos([photo?.prev_id, photo?.next_id]);

  const onUpdate = (b: PhotoUpdate) => {
    if (photo) update.mutate(b);
  };
  const older = photo?.next_id
    ? () =>
        setBrowse((b) => ({
          id: photo.next_id,
          back: b.back + 1,
          from: b.from ?? latestId,
          enter: "right",
        }))
    : null;
  const newer =
    photo?.prev_id && browse.id !== null
      ? () =>
          setBrowse((b) =>
            photo.prev_id === latestId || b.back <= 1
              ? { ...FOLLOW, enter: "left" }
              : { ...b, id: photo.prev_id, back: b.back - 1, enter: "left" },
          )
      : null;
  const toLatest = () => setBrowse({ ...FOLLOW, enter: "left" });
  const browsing = browse.id !== null;
  const arrived = browsing && browse.from !== null && latestId !== browse.from;

  useCullingKeys(photo, {
    onUpdate,
    onPrev: () => newer?.(),
    onNext: () => older?.(),
    extra: browsing ? { l: toLatest } : undefined,
  });

  return (
    <div className="mx-auto max-w-[1600px] space-y-4 p-3 sm:p-4 md:space-y-5 md:p-6">
      <h1 className="sr-only">Dashboard</h1>
      <CameraStatusBar stats={s} />

      {photo ? (
        <Card className="relative overflow-hidden" data-testid="latest-photo">
          {browsing && (
            <div className="absolute top-3 right-3 z-10 flex flex-col items-end gap-2 xl:right-[calc(380px+0.75rem)]">
              <button
                type="button"
                onClick={toLatest}
                className={cn(
                  "flex h-11 items-center gap-2 rounded-full px-4 text-sm font-semibold shadow-lg ring-1 backdrop-blur",
                  arrived
                    ? "bg-accent text-ink-950 ring-accent animate-fade-in"
                    : "bg-ink-950/85 text-ink-100 ring-ink-700",
                )}
                data-testid="back-to-latest"
              >
                <ArrowUpToLine className="size-4" />
                {arrived ? "New frame — show" : "Back to latest"}
              </button>
            </div>
          )}
          <div className="grid gap-0 xl:h-[max(34rem,calc(100svh-6.75rem))] xl:grid-cols-[minmax(0,1fr)_380px]">
            <FrameImage
              photo={photo}
              back={browse.back}
              enter={browse.enter}
              dimmed={frame.isPlaceholderData}
              onNewer={newer}
              onOlder={older}
            />
            <FrameDetails photo={photo} onUpdate={onUpdate} />
          </div>
        </Card>
      ) : stats.isLoading || frame.isLoading ? (
        <Skeleton className="h-[30rem] w-full rounded-xl" />
      ) : (
        <Card className="grid h-72 place-items-center px-6 text-center">
          <div>
            <Camera className="text-ink-300 mx-auto mb-3 size-8" />
            <p className="text-ink-100">No photos yet</p>
            <p className="text-ink-300 text-sm">
              Shoot with FTP upload enabled. New frames appear here within seconds.
            </p>
          </div>
        </Card>
      )}

      {latestId && (
        <BestPhotos receiving={s?.camera.state === "receiving"} shotToday={(s?.today.photos ?? 0) > 0} />
      )}

      <div className="grid gap-4 md:gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card>
          <CardHeader
            title="Recent"
            icon={<Images className="size-4" />}
            action={
              <Link
                href="/library"
                className={buttonClass({ size: "sm", variant: "ghost", className: "-mr-2" })}
              >
                View all
              </Link>
            }
          />
          <CardBody>
            {s?.recent.length ? (
              <div className="grid grid-cols-2 items-start gap-2.5 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">
                {s.recent.map((p) => (
                  <PhotoThumb key={p.id} photo={p} selected={p.id === photo?.id} />
                ))}
              </div>
            ) : stats.isLoading ? (
              <div className="grid grid-cols-2 items-start gap-2.5 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">
                {Array.from({ length: 4 }, (_, i) => (
                  <Skeleton key={i} className="aspect-[3/2] w-full" />
                ))}
              </div>
            ) : (
              <p className="text-ink-300 text-sm">Nothing imported yet.</p>
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Activity" icon={<Activity className="size-4" />} />
          <CardBody>
            <ActivityFeed limit={14} />
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
