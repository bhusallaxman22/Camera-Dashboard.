"use client";

import { Ban, Check, CircleSlash, Heart, PencilLine, Upload } from "lucide-react";
import type { PhotoDetail, PhotoUpdate } from "@/lib/types";
import { Button } from "./ui/button";
import { RatingStars } from "./rating-stars";

/**
 * Rating / flag / favorite / edit-state controls. State lives in the app DB
 * only — nothing is written into the original files.
 */
export function CullingControls({
  photo,
  onUpdate,
  disabled,
}: {
  photo: Pick<PhotoDetail, "rating" | "flag" | "favorite" | "needs_edit" | "exported">;
  onUpdate: (body: PhotoUpdate) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="culling-controls">
      <RatingStars value={photo.rating} onChange={(rating) => onUpdate({ rating })} />
      <span className="bg-ink-700 mx-1 h-5 w-px" />
      <Button
        size="sm"
        variant="ghost"
        disabled={disabled}
        active={photo.flag === "pick"}
        onClick={() => onUpdate({ flag: photo.flag === "pick" ? "none" : "pick" })}
        title="Pick (P)"
      >
        <Check className="size-3.5" /> Pick
      </Button>
      <Button
        size="sm"
        variant="ghost"
        disabled={disabled}
        onClick={() => onUpdate({ flag: photo.flag === "reject" ? "none" : "reject" })}
        className={photo.flag === "reject" ? "bg-bad/15 text-bad ring-bad/40 ring-1" : undefined}
        title="Reject (X)"
      >
        <Ban className="size-3.5" /> Reject
      </Button>
      {photo.flag !== "none" && (
        <Button size="sm" variant="ghost" onClick={() => onUpdate({ flag: "none" })} title="Unflag (U)">
          <CircleSlash className="size-3.5" />
        </Button>
      )}
      <span className="bg-ink-700 mx-1 h-5 w-px" />
      <Button
        size="sm"
        variant="ghost"
        disabled={disabled}
        onClick={() => onUpdate({ favorite: !photo.favorite })}
        className={photo.favorite ? "text-bad" : undefined}
        aria-pressed={photo.favorite}
        title="Favorite (F)"
      >
        <Heart className={photo.favorite ? "fill-bad size-3.5" : "size-3.5"} /> Favorite
      </Button>
      <Button
        size="sm"
        variant="ghost"
        disabled={disabled}
        active={photo.needs_edit}
        aria-pressed={photo.needs_edit}
        onClick={() => onUpdate({ needs_edit: !photo.needs_edit })}
        title="Needs edit (E)"
      >
        <PencilLine className="size-3.5" /> Needs edit
      </Button>
      <Button
        size="sm"
        variant="ghost"
        disabled={disabled}
        active={photo.exported}
        aria-pressed={photo.exported}
        onClick={() => onUpdate({ exported: !photo.exported })}
        title="Mark exported"
      >
        <Upload className="size-3.5" /> Exported
      </Button>
    </div>
  );
}
