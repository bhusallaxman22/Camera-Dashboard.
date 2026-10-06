"use client";

import { useQuery } from "@tanstack/react-query";
import { RotateCcw, Search, Star } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Input, Label, Select } from "./ui/input";

export type FilterState = Record<string, string>;

export const SORTS = [
  ["newest", "Newest first"],
  ["oldest", "Oldest first"],
  ["rating", "Rating"],
  ["sharpness", "Sharpness"],
  ["imported", "Recently imported"],
  ["filename", "Filename"],
] as const;

const QUICK: { key: string; value: string; label: string }[] = [
  { key: "flag", value: "pick", label: "Picks" },
  { key: "favorite", value: "true", label: "Favorites" },
  { key: "needs_edit", value: "true", label: "Needs edit" },
  { key: "exported", value: "true", label: "Exported" },
  { key: "hide_rejected", value: "true", label: "Hide rejects" },
  { key: "flag", value: "reject", label: "Rejects only" },
  { key: "has_faces", value: "true", label: "Faces" },
  { key: "collapse_bursts", value: "true", label: "Collapse bursts" },
];

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "h-8 shrink-0 rounded-full px-3 text-sm whitespace-nowrap transition-colors pointer-coarse:h-10",
        active
          ? "bg-accent-soft text-accent ring-accent/40 ring-1"
          : "bg-ink-850 text-ink-200 hover:bg-ink-800 ring-ink-800 ring-1",
      )}
    >
      {children}
    </button>
  );
}

export function LibraryFilters({
  value,
  onChange,
}: {
  value: FilterState;
  onChange: (next: FilterState) => void;
}) {
  const facets = useQuery({ queryKey: ["facets"], queryFn: api.facets, staleTime: 60_000 });
  const [q, setQ] = useState(value.q ?? "");

  useEffect(() => {
    if ((value.q ?? "") === q) return;
    const t = setTimeout(() => onChange({ ...value, q }), 300);
    return () => clearTimeout(t);
    // Only the debounced text should drive this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const set = (key: string, v: string | undefined) => {
    const next = { ...value };
    if (v === undefined || v === "") delete next[key];
    else next[key] = v;
    onChange(next);
  };

  const toggle = (key: string, v: string) => set(key, value[key] === v ? undefined : v);
  const activeCount = Object.keys(value).filter((k) => k !== "sort" && k !== "q").length;
  const f = facets.data;

  return (
    <div className="space-y-3" data-testid="library-filters">
      <div className="flex items-center gap-2">
        <div className="relative min-w-0 flex-1">
          <Search className="text-ink-300 pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
          <Input
            type="search"
            enterKeyHint="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search filename, lens, scene, tags, AI description…"
            className="pl-8"
            aria-label="Search"
          />
        </div>
        <Select
          value={value.sort ?? "newest"}
          onChange={(e) => set("sort", e.target.value === "newest" ? undefined : e.target.value)}
          className="w-36 shrink-0 sm:w-44"
          aria-label="Sort"
        >
          {SORTS.map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </Select>
      </div>

      <div className="-mx-3 flex scrollbar-none items-center gap-1.5 overflow-x-auto px-3 sm:mx-0 sm:flex-wrap sm:px-0">
        {QUICK.map((c) => (
          <Chip key={c.label} active={value[c.key] === c.value} onClick={() => toggle(c.key, c.value)}>
            {c.label}
          </Chip>
        ))}
        <span className="bg-ink-700 mx-1 h-4 w-px shrink-0" />
        {[1, 2, 3, 4, 5].map((n) => (
          <Chip
            key={n}
            active={value.rating_min === String(n)}
            onClick={() => toggle("rating_min", String(n))}
          >
            <span className="flex items-center gap-1">
              <Star className="size-3.5 fill-current" aria-hidden />
              <span className="tabular">
                {n}+<span className="sr-only"> stars</span>
              </span>
            </span>
          </Chip>
        ))}
        {(activeCount > 0 || value.q) && (
          <button
            type="button"
            onClick={() => {
              setQ("");
              onChange(value.sort ? { sort: value.sort } : {});
            }}
            className="text-ink-200 hover:text-ink-100 ml-1 flex h-8 shrink-0 items-center gap-1.5 px-2 text-sm pointer-coarse:h-10"
          >
            <RotateCcw className="size-4" /> Reset
          </button>
        )}
      </div>

      <details className="group border-ink-800 bg-ink-900/60 rounded-lg border">
        <summary className="text-ink-200 hover:text-ink-100 flex h-11 cursor-pointer list-none items-center px-3 text-sm select-none">
          More filters {activeCount > 0 && <span className="text-accent">· {activeCount} active</span>}
        </summary>
        <div className="grid gap-3 px-3 pb-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
          <div>
            <Label htmlFor="f-from">From</Label>
            <Input
              id="f-from"
              type="date"
              value={value.date_from ?? ""}
              onChange={(e) => set("date_from", e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="f-to">To</Label>
            <Input
              id="f-to"
              type="date"
              value={value.date_to ?? ""}
              onChange={(e) => set("date_to", e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="f-kind">Files</Label>
            <Select
              id="f-kind"
              value={value.file_kind ?? ""}
              onChange={(e) => set("file_kind", e.target.value)}
            >
              <option value="">Any</option>
              <option value="pair">RAW + JPEG</option>
              <option value="raw">Has RAW</option>
              <option value="raw_only">RAW only</option>
              <option value="jpeg_only">JPEG only</option>
              <option value="still">Stills</option>
              <option value="video">Video</option>
            </Select>
          </div>
          <div>
            <Label htmlFor="f-camera">Camera</Label>
            <Select id="f-camera" value={value.camera ?? ""} onChange={(e) => set("camera", e.target.value)}>
              <option value="">Any</option>
              {f?.cameras.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </Select>
          </div>
          <div className="lg:col-span-2">
            <Label htmlFor="f-lens">Lens</Label>
            <Select id="f-lens" value={value.lens ?? ""} onChange={(e) => set("lens", e.target.value)}>
              <option value="">Any</option>
              {f?.lenses.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="f-scene">Scene</Label>
            <Select id="f-scene" value={value.scene ?? ""} onChange={(e) => set("scene", e.target.value)}>
              <option value="">Any</option>
              {f?.scenes.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="f-tag">Tag</Label>
            <Select id="f-tag" value={value.tag ?? ""} onChange={(e) => set("tag", e.target.value)}>
              <option value="">Any</option>
              {f?.tags.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="f-iso">Max ISO</Label>
            <Input
              id="f-iso"
              type="number"
              min={50}
              step={100}
              placeholder={f?.iso_range[1] ? String(f.iso_range[1]) : "any"}
              value={value.iso_max ?? ""}
              onChange={(e) => set("iso_max", e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="f-focal-min">Focal ≥ (mm)</Label>
            <Input
              id="f-focal-min"
              type="number"
              min={1}
              value={value.focal_min ?? ""}
              onChange={(e) => set("focal_min", e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="f-focal-max">Focal ≤ (mm)</Label>
            <Input
              id="f-focal-max"
              type="number"
              min={1}
              value={value.focal_max ?? ""}
              onChange={(e) => set("focal_max", e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="f-sharp">Sharpness ≥</Label>
            <Select
              id="f-sharp"
              value={value.sharp_min ?? ""}
              onChange={(e) => set("sharp_min", e.target.value)}
            >
              <option value="">Any</option>
              <option value="35">Acceptable (35)</option>
              <option value="55">Good (55)</option>
              <option value="75">Excellent (75)</option>
            </Select>
          </div>
        </div>
      </details>
    </div>
  );
}
