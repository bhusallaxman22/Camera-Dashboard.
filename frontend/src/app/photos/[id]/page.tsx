"use client";

import { ArrowLeft, ChevronLeft, ChevronRight, Layers } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type CSSProperties } from "react";
import { AnalysisPanel } from "@/components/analysis-panel";
import { CritiquePanel } from "@/components/critique-panel";
import { CullBar, CullingControls } from "@/components/culling-controls";
import { FilesPanel } from "@/components/files-panel";
import { ExposureStrip, MetadataGrid } from "@/components/metadata-grid";
import { PhotoActions } from "@/components/photo-actions";
import { FileKindBadges, PhotoThumb } from "@/components/photo-thumb";
import { CULL_SHORTCUTS, ShortcutLegend } from "@/components/shortcut-legend";
import { TagsNotes } from "@/components/tags-notes";
import { VerdictStrip } from "@/components/verdict-strip";
import { ZoomViewer } from "@/components/zoom-viewer";
import { Badge } from "@/components/ui/badge";
import { Button, buttonClass } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { usePhoto, usePhotoUpdate, usePrefetchPhotos } from "@/lib/hooks";
import type { PhotoUpdate } from "@/lib/types";
import { useCullingKeys } from "@/lib/use-culling-keys";
import type { SwipeDir } from "@/lib/use-swipe";
import { cn } from "@/lib/utils";

const TABS = [
  ["info", "Info"],
  ["analysis", "Analysis"],
  ["ai", "AI"],
  ["files", "Files"],
] as const;
type TabKey = (typeof TABS)[number][0];

const SHORTCUTS: [string, string][] = [...CULL_SHORTCUTS, ["← / →", "Newer / older"], ["Esc", "Back"]];

// Survives the route change so the next photo can slide in from the side it came from.
let lastNav: { id: string; enter: SwipeDir } | null = null;

function DetailInner() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const search = useSearchParams();
  const qs = search.toString();
  const libraryHref = `/library${qs ? `?${qs}` : ""}`;
  const { data: photo, error, isLoading } = usePhoto(id);
  const update = usePhotoUpdate(id);
  const [tab, setTab] = useState<TabKey>("info");
  usePrefetchPhotos([photo?.prev_id, photo?.next_id]);

  const go = (target: string | null | undefined, enter: SwipeDir) => {
    if (!target) return;
    lastNav = { id: target, enter };
    router.push(`/photos/${target}${qs ? `?${qs}` : ""}`, { scroll: false });
  };
  const newer = () => go(photo?.prev_id, "left");
  const older = () => go(photo?.next_id, "right");
  const onUpdate = (b: PhotoUpdate) => update.mutate(b);
  useCullingKeys(photo, {
    onUpdate,
    onPrev: newer,
    onNext: older,
    extra: { escape: () => router.push(libraryHref) },
  });

  if (error) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="space-y-3 p-6">
        <p className="text-ink-200">
          {notFound ? "Photo not found." : `Could not load photo: ${error.message}`}
        </p>
        <Link href={libraryHref} className={buttonClass({ variant: "outline" })}>
          <ArrowLeft className="size-4" /> Back to library
        </Link>
      </div>
    );
  }
  if (isLoading || !photo) {
    return (
      <div className="grid gap-3 p-2 sm:p-3 lg:grid-cols-[minmax(0,1fr)_400px] lg:p-4">
        <Skeleton className="h-[calc(100svh-17.5rem)] w-full rounded-xl lg:h-[calc(100svh-2rem)]" />
        <Skeleton className="h-40 w-full rounded-xl lg:h-[calc(100svh-2rem)]" />
      </div>
    );
  }

  const enter = lastNav?.id === photo.id ? lastNav.enter : null;
  const files = photo.files.length;
  const ratio =
    photo.preview_width && photo.preview_height ? photo.preview_height / photo.preview_width : 2 / 3;
  // Phones: hug the frame's aspect so landscapes don't float in empty checkerboard; cap portraits.
  const fit = {
    "--fit-h": `min(calc(100svh - 17.5rem), calc((100vw - 1rem) * ${ratio.toFixed(4)}))`,
  } as CSSProperties;

  return (
    <div className="flex flex-col gap-2 p-2 pb-[calc(8.5rem+env(safe-area-inset-bottom))] sm:p-3 sm:pb-[calc(8.5rem+env(safe-area-inset-bottom))] lg:gap-3 lg:p-4">
      <div className="pt-safe flex items-center gap-1">
        <Link
          href={libraryHref}
          className={buttonClass({ size: "sm", variant: "ghost", className: "-ml-1" })}
        >
          <ArrowLeft className="size-4" /> <span className="max-sm:sr-only">Library</span>
        </Link>
        <div className="min-w-0 flex-1 px-1">
          <h1 className="truncate font-mono text-sm sm:text-base">{photo.base_filename}</h1>
          <p className="text-ink-300 tabular truncate text-xs">{formatDateTime(photo.capture_time)}</p>
        </div>
        {photo.processing_status === "pending" && <Badge tone="info">Processing</Badge>}
        {photo.processing_status === "error" && (
          <Badge tone="bad" title={photo.processing_error ?? ""}>
            Error
          </Badge>
        )}
        <Button
          size="icon"
          variant="ghost"
          disabled={!photo.prev_id}
          onClick={newer}
          aria-label="Newer photo"
        >
          <ChevronLeft className="size-5" />
        </Button>
        <Button
          size="icon"
          variant="ghost"
          disabled={!photo.next_id}
          onClick={older}
          aria-label="Older photo"
        >
          <ChevronRight className="size-5" />
        </Button>
      </div>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_400px]">
        <div className="relative min-w-0 lg:col-start-1 lg:row-start-1" style={fit}>
          <ZoomViewer
            key={photo.preview_url ?? photo.id}
            src={photo.preview_url}
            alt={photo.base_filename}
            faces={photo.analysis?.faces ?? []}
            className="h-[var(--fit-h)] min-h-48 lg:h-[calc(100svh-7rem)] lg:min-h-80"
            fitClassName="max-h-[var(--fit-h)] lg:max-h-[calc(100svh-7rem)]"
            onSwipe={(dir) => (dir === "left" ? older() : newer())}
            canSwipe={(dir) => Boolean(dir === "left" ? photo.next_id : photo.prev_id)}
            enter={enter}
          />
          <FileKindBadges photo={photo} className="pointer-events-none absolute top-2 left-2" />
        </div>

        <aside className="flex min-w-0 flex-col gap-3 lg:col-start-2 lg:row-span-2 lg:row-start-1">
          <section className="border-ink-800 bg-ink-900/80 space-y-3 rounded-xl border p-3">
            <VerdictStrip photo={photo} />
            <p className="text-ink-300 truncate text-sm">
              {[photo.camera, photo.lens_model].filter(Boolean).join(" · ") || "Unknown camera"}
            </p>
            <ExposureStrip photo={photo} />
            <CullingControls
              photo={photo}
              onUpdate={onUpdate}
              withCullBar
              extra={
                <>
                  <PhotoActions photo={photo} className="contents" />
                  <ShortcutLegend shortcuts={SHORTCUTS} />
                </>
              }
            />
          </section>

          <section className="border-ink-800 bg-ink-900/80 flex-1 rounded-xl border">
            <div role="tablist" aria-label="Photo details" className="border-ink-800 flex border-b px-1">
              {TABS.map(([k, label]) => (
                <button
                  key={k}
                  id={`tab-${k}`}
                  role="tab"
                  aria-selected={tab === k}
                  aria-controls={`panel-${k}`}
                  onClick={() => setTab(k)}
                  className={cn(
                    "-mb-px flex h-11 flex-1 items-center justify-center gap-1 border-b-2 px-2 text-sm font-medium",
                    tab === k
                      ? "border-accent text-ink-100"
                      : "text-ink-300 hover:text-ink-100 border-transparent",
                  )}
                >
                  {label}
                  {k === "files" && <span className="text-ink-300 tabular">{files}</span>}
                </button>
              ))}
            </div>
            <div
              id={`panel-${tab}`}
              role="tabpanel"
              aria-labelledby={`tab-${tab}`}
              className="min-h-48 p-4 lg:max-h-[calc(100svh-30rem)] lg:min-h-64 lg:overflow-y-auto"
            >
              {tab === "info" && (
                <div className="space-y-5">
                  <TagsNotes key={photo.id} tags={photo.tags} notes={photo.notes} onUpdate={onUpdate} />
                  <MetadataGrid photo={photo} />
                </div>
              )}
              {tab === "analysis" && <AnalysisPanel analysis={photo.analysis} />}
              {tab === "ai" && <CritiquePanel critique={photo.critique} history={photo.critique_history} />}
              {tab === "files" && <FilesPanel files={photo.files} />}
            </div>
          </section>
        </aside>

        {photo.burst && photo.burst.members.length > 1 && (
          <section className="border-ink-800 bg-ink-900/80 min-w-0 rounded-xl border p-3 lg:col-start-1 lg:row-start-2">
            <h2 className="text-ink-200 mb-2 flex items-center gap-2 text-sm font-medium">
              <Layers className="text-ink-300 size-4" /> Burst · {photo.burst.photo_count} frames
            </h2>
            <div className="-mx-1 flex snap-x scrollbar-none gap-2 overflow-x-auto px-1 pb-1">
              {photo.burst.members.map((m) => (
                <PhotoThumb
                  key={m.id}
                  photo={m}
                  href={`/photos/${m.id}${qs ? `?${qs}` : ""}`}
                  selected={m.id === photo.id}
                  showMeta={false}
                  className="w-28 shrink-0 snap-start"
                />
              ))}
            </div>
          </section>
        )}
      </div>

      <CullBar photo={photo} onUpdate={onUpdate} className="lg:hidden" />
    </div>
  );
}

export default function PhotoDetailPage() {
  return (
    <Suspense fallback={null}>
      <DetailInner />
    </Suspense>
  );
}
