"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { Grid2x2, Grid3x3, Loader2 } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LibraryFilters, type FilterState } from "@/components/library-filters";
import { PhotoThumb } from "@/components/photo-thumb";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 60;

const DENSITY = {
  large: { grid: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5", thumb: 1024 },
  medium: { grid: "grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 2xl:grid-cols-8", thumb: 512 },
} as const;

function LibraryInner() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [density, setDensity] = useState<keyof typeof DENSITY>("medium");

  const filters = useMemo<FilterState>(() => Object.fromEntries(params.entries()), [params]);

  const setFilters = useCallback(
    (next: FilterState) => {
      const qs = new URLSearchParams(next).toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [router, pathname],
  );

  const query = useInfiniteQuery({
    queryKey: ["photos", "library", filters, density],
    queryFn: ({ pageParam }) =>
      api.photos({ ...filters, page: pageParam, page_size: PAGE_SIZE, thumb: DENSITY[density].thumb }),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.has_more ? last.page + 1 : undefined),
  });

  const sentinel = useRef<HTMLDivElement>(null);
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = query;
  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasNextPage && !isFetchingNextPage) void fetchNextPage();
      },
      { rootMargin: "800px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const items = query.data?.pages.flatMap((p) => p.items) ?? [];
  const total = query.data?.pages[0]?.total ?? 0;
  const detailQs = params.toString();

  return (
    <div className="mx-auto max-w-[1800px] space-y-4 p-4 md:p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Library</h1>
          <p className="text-ink-400 tabular text-sm" data-testid="library-count">
            {query.isLoading ? "Loading…" : `${total.toLocaleString()} photo${total === 1 ? "" : "s"}`}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <Button
            size="icon"
            variant="ghost"
            active={density === "large"}
            onClick={() => setDensity("large")}
            aria-label="Large thumbnails"
          >
            <Grid2x2 className="size-4" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            active={density === "medium"}
            onClick={() => setDensity("medium")}
            aria-label="Small thumbnails"
          >
            <Grid3x3 className="size-4" />
          </Button>
        </div>
      </div>

      <LibraryFilters value={filters} onChange={setFilters} />

      {query.isError && (
        <div className="border-bad/30 bg-bad/5 text-bad rounded-lg border p-3 text-sm">
          Could not load photos: {query.error instanceof Error ? query.error.message : "unknown error"}
        </div>
      )}

      {query.isLoading ? (
        <div className={cn("grid gap-2.5", DENSITY[density].grid)}>
          {Array.from({ length: 18 }, (_, i) => (
            <Skeleton key={i} className="aspect-[3/2] w-full rounded-lg" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="border-ink-800 text-ink-500 grid h-60 place-items-center rounded-xl border border-dashed text-sm">
          No photos match these filters.
        </div>
      ) : (
        <div className={cn("grid gap-2.5", DENSITY[density].grid)} data-testid="library-grid">
          {items.map((p) => (
            <PhotoThumb key={p.id} photo={p} href={`/photos/${p.id}${detailQs ? `?${detailQs}` : ""}`} />
          ))}
        </div>
      )}

      <div ref={sentinel} className="flex h-16 items-center justify-center">
        {isFetchingNextPage && <Loader2 className="text-ink-500 size-5 animate-spin" />}
      </div>
    </div>
  );
}

export default function LibraryPage() {
  return (
    <Suspense fallback={<div className="text-ink-500 p-6 text-sm">Loading…</div>}>
      <LibraryInner />
    </Suspense>
  );
}
