"use client";

import { Copy, Download, ExternalLink, RefreshCw, Search, Sparkles } from "lucide-react";
import { useAnalyze, useCopy, useLinkImmich } from "@/lib/hooks";
import type { PhotoDetail } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button, buttonClass } from "./ui/button";

export function primaryFiles(photo: PhotoDetail) {
  const live = photo.files.filter((f) => f.exists && !f.is_duplicate);
  return {
    jpeg: live.find((f) => f.file_type === "jpeg" || f.file_type === "image"),
    raw: live.find((f) => f.file_type === "raw"),
    video: live.find((f) => f.file_type === "video"),
  };
}

export function PhotoActions({
  photo,
  compact,
  className,
}: {
  photo: PhotoDetail;
  compact?: boolean;
  className?: string;
}) {
  const analyze = useAnalyze(photo.id);
  const linkImmich = useLinkImmich(photo.id);
  const copy = useCopy();
  const { jpeg, raw, video } = primaryFiles(photo);
  const editPath = raw ?? jpeg ?? video;

  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)} data-testid="photo-actions">
      {jpeg && (
        <a
          href={jpeg.download_url}
          download={jpeg.filename}
          className={buttonClass({ size: "sm", variant: "ghost" })}
        >
          <Download className="size-4" /> JPEG
        </a>
      )}
      {raw && (
        <a
          href={raw.download_url}
          download={raw.filename}
          className={buttonClass({ size: "sm", variant: "ghost" })}
        >
          <Download className="size-4" /> RAW
        </a>
      )}
      {video && (
        <a
          href={video.download_url}
          download={video.filename}
          className={buttonClass({ size: "sm", variant: "ghost" })}
        >
          <Download className="size-4" /> Video
        </a>
      )}
      {editPath && (
        <Button
          size="sm"
          variant="ghost"
          onClick={() =>
            copy(editPath.smb_path ?? editPath.nas_path, editPath.smb_path ? "SMB path" : "NAS path")
          }
          title={editPath.smb_path ?? editPath.nas_path}
        >
          <Copy className="size-4" /> {compact ? "Path" : "Copy editor path"}
        </Button>
      )}
      <Button
        size="sm"
        variant="ghost"
        disabled={analyze.isPending}
        onClick={() => analyze.mutate({ technical: true, ai: true })}
        title="Re-run technical analysis and AI critique"
      >
        <Sparkles className="size-4" /> {compact ? "Analyze" : "Re-analyze"}
      </Button>
      {!compact && (
        <Button
          size="sm"
          variant="ghost"
          disabled={analyze.isPending}
          onClick={() => analyze.mutate({ rerender: true, ai: false })}
          title="Regenerate preview & thumbnails"
          className="max-lg:hidden"
        >
          <RefreshCw className="size-4" /> Re-render
        </Button>
      )}
      {photo.immich_url ? (
        <a
          href={photo.immich_url}
          target="_blank"
          rel="noreferrer"
          className={buttonClass({ size: "sm", variant: "ghost" })}
        >
          <ExternalLink className="size-4" /> Open in Immich
        </a>
      ) : (
        photo.immich_enabled &&
        jpeg && (
          <Button
            size="sm"
            variant="ghost"
            disabled={linkImmich.isPending}
            onClick={() => linkImmich.mutate()}
            title="Look up this JPEG in Immich (read-only)"
          >
            <Search className="size-4" /> Find in Immich
          </Button>
        )
      )}
    </div>
  );
}
