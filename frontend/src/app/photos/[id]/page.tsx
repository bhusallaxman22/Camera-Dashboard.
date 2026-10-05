"use client";

import { ArrowLeft, ChevronLeft, ChevronRight, Keyboard, Layers } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { AnalysisPanel } from "@/components/analysis-panel";
import { CritiquePanel } from "@/components/critique-panel";
import { CullingControls } from "@/components/culling-controls";
import { FilesPanel } from "@/components/files-panel";
import { ExposureStrip, MetadataGrid } from "@/components/metadata-grid";
import { PhotoActions } from "@/components/photo-actions";
import { FileKindBadges, PhotoThumb } from "@/components/photo-thumb";
import { TagsNotes } from "@/components/tags-notes";
import { ZoomViewer } from "@/components/zoom-viewer";
import { Badge } from "@/components/ui/badge";
import { Button, buttonClass } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { usePhoto, usePhotoUpdate } from "@/lib/hooks";
import type { PhotoDetail, PhotoUpdate } from "@/lib/types";
import { cn } from "@/lib/utils";

const TABS = [
  ["info", "Info"],
  ["analysis", "Analysis"],
  ["ai", "AI"],
  ["files", "Files"],
] as const;
type TabKey = (typeof TABS)[number][0];

const SHORTCUTS: [string, string][] = [
  ["0–5", "Rating"],
  ["P / X / U", "Pick / reject / unflag"],
  ["F", "Favorite"],
  ["E", "Needs edit"],
  ["← / →", "Newer / older"],
  ["Esc", "Back to library"],
];

function useCullingKeys(
  photo: PhotoDetail | undefined,
  onUpdate: (b: PhotoUpdate) => void,
  go: (id: string | null) => void,
  back: () => void,
) {
  useEffect(() => {
    if (!photo) return;
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)))
        return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (/^[0-5]$/.test(k)) onUpdate({ rating: Number(k) });
      else if (k === "p") onUpdate({ flag: photo.flag === "pick" ? "none" : "pick" });
      else if (k === "x") onUpdate({ flag: photo.flag === "reject" ? "none" : "reject" });
      else if (k === "u") onUpdate({ flag: "none" });
      else if (k === "f") onUpdate({ favorite: !photo.favorite });
      else if (k === "e") onUpdate({ needs_edit: !photo.needs_edit });
      else if (k === "arrowleft") go(photo.prev_id);
      else if (k === "arrowright") go(photo.next_id);
      else if (k === "escape") back();
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [photo, onUpdate, go, back]);
}

function DetailInner() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const search = useSearchParams();
  const qs = search.toString();
  const libraryHref = `/library${qs ? `?${qs}` : ""}`;
  const { data: photo, error, isLoading } = usePhoto(id);
  const update = usePhotoUpdate(id);
  const [tab, setTab] = useState<TabKey>("info");
  const [showKeys, setShowKeys] = useState(false);

  const go = (target: string | null) => {
    if (target) router.push(`/photos/${target}${qs ? `?${qs}` : ""}`, { scroll: false });
  };
  const onUpdate = (b: PhotoUpdate) => update.mutate(b);
  useCullingKeys(photo, onUpdate, go, () => router.push(libraryHref));

  if (error) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="p-6">
        <p className="text-ink-300">
          {notFound ? "Photo not found." : `Could not load photo: ${error.message}`}
        </p>
        <Link href={libraryHref} className="text-accent text-sm">
          Back to library
        </Link>
      </div>
    );
  }
  if (isLoading || !photo) {
    return (
      <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_400px]">
        <Skeleton className="h-[75vh] w-full rounded-xl" />
        <Skeleton className="h-[75vh] w-full rounded-xl" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 p-3 md:p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Link href={libraryHref} className={buttonClass({ size: "sm", variant: "ghost" })}>
          <ArrowLeft className="size-4" /> Library
        </Link>
        <div className="flex items-center">
          <Button
            size="icon"
            variant="ghost"
            disabled={!photo.prev_id}
            onClick={() => go(photo.prev_id)}
            aria-label="Newer photo"
          >
            <ChevronLeft className="size-4" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            disabled={!photo.next_id}
            onClick={() => go(photo.next_id)}
            aria-label="Older photo"
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
        <h1 className="font-mono text-base">{photo.base_filename}</h1>
        <FileKindBadges photo={photo} />
        {photo.processing_status === "pending" && <Badge tone="info">Processing</Badge>}
        {photo.processing_status === "error" && (
          <Badge tone="bad" title={photo.processing_error ?? ""}>
            Error
          </Badge>
        )}
        <span className="text-ink-400 text-xs">{formatDateTime(photo.capture_time)}</span>
        <div className="ml-auto flex items-center gap-1">
          <Button
            size="icon"
            variant="ghost"
            onClick={() => setShowKeys((v) => !v)}
            aria-label="Keyboard shortcuts"
            active={showKeys}
          >
            <Keyboard className="size-4" />
          </Button>
        </div>
      </div>

      {showKeys && (
        <div className="border-ink-800 bg-ink-900 text-ink-300 flex flex-wrap gap-x-5 gap-y-1 rounded-lg border px-3 py-2 text-xs">
          {SHORTCUTS.map(([k, label]) => (
            <span key={k}>
              <kbd className="bg-ink-800 text-ink-100 rounded px-1.5 py-0.5 font-mono">{k}</kbd> {label}
            </span>
          ))}
        </div>
      )}

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_400px]">
        <div className="flex min-w-0 flex-col gap-3">
          <ZoomViewer
            key={photo.preview_url ?? photo.id}
            src={photo.preview_url}
            alt={photo.base_filename}
            faces={photo.analysis?.faces ?? []}
            className="h-[calc(100vh-11rem)] min-h-80"
          />
          {photo.burst && photo.burst.members.length > 1 && (
            <div className="border-ink-800 bg-ink-900/80 rounded-xl border p-3">
              <div className="text-ink-400 mb-2 flex items-center gap-2 text-[11px] font-semibold tracking-[0.12em] uppercase">
                <Layers className="size-3.5" /> Burst · {photo.burst.photo_count} frames
              </div>
              <div className="flex gap-2 overflow-x-auto pb-1">
                {photo.burst.members.map((m) => (
                  <PhotoThumb
                    key={m.id}
                    photo={m}
                    href={`/photos/${m.id}${qs ? `?${qs}` : ""}`}
                    selected={m.id === photo.id}
                    showMeta={false}
                    className="w-28 shrink-0"
                  />
                ))}
              </div>
            </div>
          )}
        </div>

        <aside className="flex min-w-0 flex-col gap-3">
          <div className="border-ink-800 bg-ink-900/80 space-y-3 rounded-xl border p-3">
            <p className="text-ink-300 truncate text-sm">
              {[photo.camera, photo.lens_model].filter(Boolean).join(" · ") || "Unknown camera"}
            </p>
            <ExposureStrip photo={photo} />
            <CullingControls photo={photo} onUpdate={onUpdate} />
            <PhotoActions photo={photo} />
          </div>

          <div className="border-ink-800 bg-ink-900/80 flex-1 rounded-xl border">
            <div role="tablist" className="border-ink-800 flex gap-1 border-b px-2 pt-2">
              {TABS.map(([k, label]) => (
                <button
                  key={k}
                  role="tab"
                  aria-selected={tab === k}
                  onClick={() => setTab(k)}
                  className={cn(
                    "-mb-px border-b-2 px-3 py-2 text-xs font-semibold tracking-wider uppercase",
                    tab === k
                      ? "border-accent text-ink-100"
                      : "text-ink-500 hover:text-ink-300 border-transparent",
                  )}
                >
                  {label}
                  {k === "files" && <span className="text-ink-500 ml-1">{photo.files.length}</span>}
                </button>
              ))}
            </div>
            <div className="max-h-[calc(100vh-24rem)] min-h-64 overflow-y-auto p-4">
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
          </div>
        </aside>
      </div>
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
