"use client";

import { Ban, Check, Heart, PencilLine, Upload } from "lucide-react";
import type { ReactNode } from "react";
import { haptic } from "@/lib/haptics";
import type { PhotoDetail, PhotoUpdate } from "@/lib/types";
import { cn } from "@/lib/utils";
import { RatingStars } from "./rating-stars";
import { Button } from "./ui/button";

type CullState = Pick<PhotoDetail, "rating" | "flag" | "favorite" | "needs_edit" | "exported">;

interface CullProps {
  photo: CullState;
  onUpdate: (body: PhotoUpdate) => void;
  disabled?: boolean;
}

function withHaptic(onUpdate: (body: PhotoUpdate) => void) {
  return (body: PhotoUpdate) => {
    haptic(body.flag === "reject" ? [8, 40, 8] : 10);
    onUpdate(body);
  };
}

/** Pick and Reject in fixed slots; tapping the active one clears the flag. */
export function FlagToggle({
  photo,
  onUpdate,
  disabled,
  size = "md",
  className,
}: CullProps & { size?: "md" | "lg"; className?: string }) {
  const act = withHaptic(onUpdate);
  const base = cn(
    "flex items-center justify-center gap-2 rounded-lg font-semibold ring-1 transition-colors active:scale-[0.98] disabled:opacity-40",
    size === "lg" ? "h-14 text-base" : "h-11 text-sm pointer-coarse:h-14 pointer-coarse:text-base",
  );
  const icon = size === "lg" ? "size-5" : "size-4 pointer-coarse:size-5";
  const rejected = photo.flag === "reject";
  const picked = photo.flag === "pick";
  return (
    <div className={cn("grid grid-cols-2 gap-2", className)}>
      <button
        type="button"
        disabled={disabled}
        aria-pressed={rejected}
        onClick={() => act({ flag: rejected ? "none" : "reject" })}
        title="Reject (X)"
        className={cn(
          base,
          rejected ? "bg-bad/20 text-bad ring-bad/60" : "bg-ink-800 text-ink-100 ring-bad/30 hover:bg-bad/10",
        )}
      >
        <Ban className={cn(icon, "text-bad")} strokeWidth={2.25} /> Reject
      </button>
      <button
        type="button"
        disabled={disabled}
        aria-pressed={picked}
        onClick={() => act({ flag: picked ? "none" : "pick" })}
        title="Pick (P)"
        className={cn(
          base,
          picked ? "bg-ok/20 text-ok ring-ok/60" : "bg-ink-800 text-ink-100 ring-ok/30 hover:bg-ok/10",
        )}
      >
        <Check className={cn(icon, "text-ok")} strokeWidth={2.5} /> Pick
      </button>
    </div>
  );
}

export function FavoriteButton({
  photo,
  onUpdate,
  disabled,
  labelled = true,
  className,
}: CullProps & { labelled?: boolean; className?: string }) {
  const act = withHaptic(onUpdate);
  return (
    <Button
      size={labelled ? "sm" : "icon"}
      variant="ghost"
      disabled={disabled}
      onClick={() => act({ favorite: !photo.favorite })}
      className={cn(photo.favorite && "text-accent", !labelled && "size-11", className)}
      aria-pressed={photo.favorite}
      aria-label={labelled ? undefined : "Favorite"}
      title="Favorite (F)"
    >
      <Heart className={cn(labelled ? "size-4" : "size-5", photo.favorite && "fill-accent")} />
      {labelled && "Favorite"}
    </Button>
  );
}

/** Lower-frequency states: favorite, needs edit, exported, plus any trailing actions in the same row. */
export function SecondaryFlags({
  photo,
  onUpdate,
  disabled,
  favoriteClassName,
  children,
}: CullProps & { favoriteClassName?: string; children?: ReactNode }) {
  const act = withHaptic(onUpdate);
  return (
    <div className="flex flex-wrap items-center gap-1.5 pointer-coarse:gap-1">
      <FavoriteButton photo={photo} onUpdate={onUpdate} disabled={disabled} className={favoriteClassName} />
      <Button
        size="sm"
        variant="ghost"
        disabled={disabled}
        active={photo.needs_edit}
        aria-pressed={photo.needs_edit}
        onClick={() => act({ needs_edit: !photo.needs_edit })}
        title="Needs edit (E)"
      >
        <PencilLine className="size-4" /> Needs edit
      </Button>
      <Button
        size="sm"
        variant="ghost"
        disabled={disabled}
        active={photo.exported}
        aria-pressed={photo.exported}
        onClick={() => act({ exported: !photo.exported })}
        title="Mark exported"
      >
        <Upload className="size-4" /> Exported
      </Button>
      {children}
    </div>
  );
}

/**
 * Rating / flag / favorite / edit-state controls. State lives in the app DB
 * only — nothing is written into the original files.
 */
export function CullingControls({
  photo,
  onUpdate,
  disabled,
  extra,
  withCullBar = false,
}: CullProps & { extra?: ReactNode; withCullBar?: boolean }) {
  // Below lg a CullBar already carries stars, Pick/Reject and favorite.
  const barOwned = withCullBar ? "max-lg:hidden" : undefined;
  return (
    <div className="space-y-2.5" data-testid="culling-controls">
      <RatingStars
        value={photo.rating}
        onChange={(rating) => withHaptic(onUpdate)({ rating })}
        className={cn("-ml-1.5", barOwned)}
      />
      <FlagToggle photo={photo} onUpdate={onUpdate} disabled={disabled} className={barOwned} />
      <SecondaryFlags photo={photo} onUpdate={onUpdate} disabled={disabled} favoriteClassName={barOwned}>
        {extra}
      </SecondaryFlags>
    </div>
  );
}

/** Thumb-zone culling console pinned to the bottom of the screen on phones. */
export function CullBar({ photo, onUpdate, disabled, className }: CullProps & { className?: string }) {
  return (
    <div
      className={cn(
        "border-ink-800 bg-ink-950/95 pb-safe fixed inset-x-0 bottom-0 z-30 border-t backdrop-blur",
        className,
      )}
      data-testid="cull-bar"
    >
      <div className="mx-auto max-w-xl space-y-1.5 px-3 pt-1.5 pb-2">
        <div className="flex items-center justify-between">
          <RatingStars
            value={photo.rating}
            onChange={(rating) => withHaptic(onUpdate)({ rating })}
            size="lg"
            className="-ml-1.5"
          />
          <FavoriteButton photo={photo} onUpdate={onUpdate} disabled={disabled} labelled={false} />
        </div>
        <FlagToggle photo={photo} onUpdate={onUpdate} disabled={disabled} size="lg" />
      </div>
    </div>
  );
}
