"use client";

import { Ban, Check, Film, Heart, ImageOff, Layers, Loader2, PencilLine } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { exposureLine, formatTime } from "@/lib/format";
import type { PhotoSummary } from "@/lib/types";
import { cn } from "@/lib/utils";
import { RatingStars } from "./rating-stars";

const TAG = "bg-ink-950/85 rounded px-1.5 py-px text-xs leading-4 font-bold tracking-wide";

export function FileKindBadges({ photo, className }: { photo: PhotoSummary; className?: string }) {
  return (
    <span className={cn("inline-flex gap-1", className)}>
      {photo.has_raw && <span className={cn(TAG, "text-accent")}>RAW</span>}
      {photo.has_jpeg && <span className={cn(TAG, "text-ink-100")}>JPG</span>}
      {photo.has_video && <span className={cn(TAG, "text-info")}>VID</span>}
    </span>
  );
}

export function PhotoThumb({
  photo,
  href,
  selected,
  className,
  showMeta = true,
}: {
  photo: PhotoSummary;
  href?: string;
  selected?: boolean;
  className?: string;
  showMeta?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  const target = href ?? `/photos/${photo.id}`;
  // Uniform 3:2 cells keep grid rows level; portrait frames are fitted rather than cropped.
  const portrait = Boolean(photo.thumb_width && photo.thumb_height && photo.thumb_height > photo.thumb_width);

  return (
    <Link
      href={target}
      data-testid="photo-thumb"
      aria-current={selected ? "true" : undefined}
      className={cn(
        "group bg-ink-850 ring-ink-800 hover:ring-ink-500 relative block overflow-hidden rounded-lg ring-1 transition",
        selected && "ring-accent ring-2",
        photo.rejected && "opacity-45 hover:opacity-90",
        className,
      )}
    >
      <div className={cn("relative aspect-[3/2] w-full", portrait && "bg-ink-950")}>
        {photo.thumb_url && !failed ? (
          <img
            src={photo.thumb_url}
            alt={photo.base_filename}
            loading="lazy"
            decoding="async"
            onError={() => setFailed(true)}
            className={cn(
              "absolute inset-0 size-full transition-transform duration-300 group-hover:scale-[1.02]",
              portrait ? "object-contain" : "object-cover",
            )}
          />
        ) : (
          <div className="text-ink-300 absolute inset-0 grid place-items-center">
            {photo.processing_status === "pending" ? (
              <Loader2 className="size-5 animate-spin" />
            ) : photo.media_type === "video" ? (
              <Film className="size-6" />
            ) : (
              <ImageOff className="size-6" />
            )}
          </div>
        )}

        <div className="absolute top-1.5 left-1.5 flex items-center gap-1">
          <FileKindBadges photo={photo} />
          {photo.burst_group_id && photo.burst_index != null && (
            <span
              className={cn(TAG, "text-ink-100 tabular flex items-center gap-0.5 font-semibold")}
              title={`Burst frame ${photo.burst_index + 1}${photo.burst_size ? ` of ${photo.burst_size}` : ""}`}
            >
              <Layers className="size-3" />
              {photo.burst_index + 1}
              {photo.burst_size ? `/${photo.burst_size}` : ""}
            </span>
          )}
        </div>

        <div className="absolute top-1.5 right-1.5 flex items-center gap-1">
          {photo.picked && (
            <span className="bg-ok text-ink-950 grid size-5 place-items-center rounded-full" title="Pick">
              <Check className="size-3" strokeWidth={3} />
            </span>
          )}
          {photo.rejected && (
            <span
              className="bg-bad text-ink-950 grid size-5 place-items-center rounded-full"
              title="Rejected"
            >
              <Ban className="size-3" strokeWidth={3} />
            </span>
          )}
          {photo.favorite && (
            <Heart className="fill-accent text-accent size-4 drop-shadow" aria-label="Favorite" />
          )}
          {photo.needs_edit && (
            <PencilLine className="text-info size-4 drop-shadow" aria-label="Needs edit" />
          )}
        </div>

        {photo.processing_status === "error" && (
          <span className="bg-bad text-ink-950 absolute bottom-1.5 left-1.5 rounded px-1.5 text-xs font-bold">
            Error
          </span>
        )}
      </div>

      {showMeta && (
        <div className="space-y-0.5 px-2 py-1.5">
          <div className="flex min-w-0 items-center justify-between gap-2">
            <span className="text-ink-100 min-w-0 truncate font-mono text-xs">{photo.base_filename}</span>
            {photo.rating > 0 && <RatingStars value={photo.rating} size="sm" className="shrink-0" />}
          </div>
          <div className="text-ink-300 flex min-w-0 items-center justify-between gap-2 text-xs">
            <span className="min-w-0 truncate">{exposureLine(photo) || photo.media_type}</span>
            <span className="tabular shrink-0 max-[420px]:hidden">{formatTime(photo.capture_time)}</span>
          </div>
        </div>
      )}
    </Link>
  );
}
