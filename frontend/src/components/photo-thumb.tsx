"use client";

import { Ban, Check, Film, Heart, ImageOff, Layers, Loader2, PencilLine } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { exposureLine, formatTime } from "@/lib/format";
import type { PhotoSummary } from "@/lib/types";
import { cn } from "@/lib/utils";
import { RatingStars } from "./rating-stars";

export function FileKindBadges({ photo, className }: { photo: PhotoSummary; className?: string }) {
  return (
    <span className={cn("inline-flex gap-1", className)}>
      {photo.has_raw && (
        <span className="bg-ink-950/80 text-accent rounded px-1 py-px text-[9px] font-bold tracking-wider">
          RAW
        </span>
      )}
      {photo.has_jpeg && (
        <span className="bg-ink-950/80 text-ink-200 rounded px-1 py-px text-[9px] font-bold tracking-wider">
          JPG
        </span>
      )}
      {photo.has_video && (
        <span className="bg-ink-950/80 text-info rounded px-1 py-px text-[9px] font-bold tracking-wider">
          VID
        </span>
      )}
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
  const aspect =
    photo.thumb_width && photo.thumb_height ? `${photo.thumb_width} / ${photo.thumb_height}` : "3 / 2";

  return (
    <Link
      href={target}
      data-testid="photo-thumb"
      className={cn(
        "group bg-ink-850 ring-ink-800 hover:ring-ink-500 relative block overflow-hidden rounded-lg ring-1 transition",
        selected && "ring-accent ring-2",
        photo.rejected && "opacity-45 hover:opacity-90",
        className,
      )}
    >
      <div className="relative w-full" style={{ aspectRatio: aspect }}>
        {photo.thumb_url && !failed ? (
          <img
            src={photo.thumb_url}
            alt={photo.base_filename}
            loading="lazy"
            decoding="async"
            onError={() => setFailed(true)}
            className="absolute inset-0 size-full object-cover transition-transform duration-300 group-hover:scale-[1.02]"
          />
        ) : (
          <div className="text-ink-500 absolute inset-0 grid place-items-center">
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
              className="bg-ink-950/80 text-ink-200 tabular flex items-center gap-0.5 rounded px-1 py-px text-[9px] font-semibold"
              title={`Burst frame ${photo.burst_index + 1}${photo.burst_size ? ` of ${photo.burst_size}` : ""}`}
            >
              <Layers className="size-2.5" />
              {photo.burst_index + 1}
              {photo.burst_size ? `/${photo.burst_size}` : ""}
            </span>
          )}
        </div>

        <div className="absolute top-1.5 right-1.5 flex items-center gap-1">
          {photo.picked && (
            <span className="bg-ok/90 text-ink-950 grid size-5 place-items-center rounded-full" title="Pick">
              <Check className="size-3" strokeWidth={3} />
            </span>
          )}
          {photo.rejected && (
            <span
              className="bg-bad/90 text-ink-950 grid size-5 place-items-center rounded-full"
              title="Rejected"
            >
              <Ban className="size-3" strokeWidth={3} />
            </span>
          )}
          {photo.favorite && <Heart className="fill-bad text-bad size-4 drop-shadow" aria-label="Favorite" />}
          {photo.needs_edit && (
            <PencilLine className="text-info size-4 drop-shadow" aria-label="Needs edit" />
          )}
        </div>

        {photo.processing_status === "error" && (
          <span className="bg-bad/90 text-ink-950 absolute bottom-1.5 left-1.5 rounded px-1 text-[9px] font-bold">
            ERROR
          </span>
        )}
      </div>

      {showMeta && (
        <div className="space-y-0.5 px-2 py-1.5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-ink-200 truncate font-mono text-[11px]">{photo.base_filename}</span>
            {photo.rating > 0 && <RatingStars value={photo.rating} size="sm" />}
          </div>
          <div className="text-ink-400 flex items-center justify-between gap-2 text-[10px]">
            <span className="truncate">{exposureLine(photo) || photo.media_type}</span>
            <span className="tabular shrink-0">{formatTime(photo.capture_time)}</span>
          </div>
        </div>
      )}
    </Link>
  );
}
