"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { useToast } from "@/components/ui/toast";
import { api } from "./api";
import type { BestPeriod, PhotoDetail, PhotoUpdate } from "./types";

export function usePhoto(id: string | null | undefined, { keepPrevious = false } = {}) {
  return useQuery({
    queryKey: ["photo", id],
    queryFn: () => api.photo(id as string),
    enabled: Boolean(id),
    placeholderData: keepPrevious ? (prev) => prev : undefined,
  });
}

/** Warm the detail and preview of neighbouring photos so a swipe lands instantly. */
export function usePrefetchPhotos(ids: (string | null | undefined)[]) {
  const qc = useQueryClient();
  const key = ids.filter(Boolean).join(",");
  useEffect(() => {
    if (!key) return;
    for (const id of key.split(",")) {
      void qc
        .prefetchQuery({ queryKey: ["photo", id], queryFn: () => api.photo(id), staleTime: 30_000 })
        .then(() => {
          const url = qc.getQueryData<PhotoDetail>(["photo", id])?.preview_url;
          if (url) new Image().src = url;
        });
    }
  }, [key, qc]);
}

/** Lives under the "photos" key so live photo events refresh the ranking. */
export function useBestPhotos(period: BestPeriod) {
  return useQuery({
    queryKey: ["photos", "best", period],
    queryFn: () => api.best(period),
    placeholderData: (prev) => prev,
  });
}

export function useStats() {
  return useQuery({ queryKey: ["stats"], queryFn: api.stats, refetchInterval: 30_000 });
}

/** PATCH a photo with optimistic UI; culling must feel instant. */
export function usePhotoUpdate(id: string) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (body: PhotoUpdate) => api.updatePhoto(id, body),
    onMutate: async (body) => {
      await qc.cancelQueries({ queryKey: ["photo", id] });
      const previous = qc.getQueryData<PhotoDetail>(["photo", id]);
      if (previous) {
        const next: PhotoDetail = { ...previous, ...body, tags: previous.tags } as PhotoDetail;
        if (body.flag) {
          next.picked = body.flag === "pick";
          next.rejected = body.flag === "reject";
        }
        qc.setQueryData(["photo", id], next);
      }
      return { previous };
    },
    onError: (err, _body, ctx) => {
      if (ctx?.previous) qc.setQueryData(["photo", id], ctx.previous);
      toast(`Update failed: ${err instanceof Error ? err.message : String(err)}`, "error");
    },
    onSuccess: (data) => {
      qc.setQueryData(["photo", id], data);
      qc.invalidateQueries({ queryKey: ["photos"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });
}

export function useAnalyze(id: string) {
  const toast = useToast();
  return useMutation({
    mutationFn: (body: Parameters<typeof api.analyze>[1]) => api.analyze(id, body),
    onSuccess: (r) =>
      toast(
        r.queued.length ? `Queued ${r.queued.length} job(s)` : "Already queued",
        r.queued.length ? "ok" : "info",
      ),
    onError: (err) => toast(`Analyze failed: ${err instanceof Error ? err.message : String(err)}`, "error"),
  });
}

export function useLinkImmich(id: string) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: () => api.linkImmich(id),
    onSuccess: (data) => {
      qc.setQueryData(["photo", id], data);
      toast("Linked to Immich", "ok");
    },
    onError: (err) => toast(`Immich: ${err instanceof Error ? err.message : String(err)}`, "error"),
  });
}

export function useCopy() {
  const toast = useToast();
  return useCallback(
    async (text: string, label = "Path") => {
      try {
        await navigator.clipboard.writeText(text);
        toast(`${label} copied`, "ok");
      } catch {
        // Clipboard API needs a secure context; plain-HTTP LAN access falls back.
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        const ok = document.execCommand("copy");
        ta.remove();
        toast(ok ? `${label} copied` : "Copy failed — select the text manually", ok ? "ok" : "error");
      }
    },
    [toast],
  );
}

/** Re-render every `ms` so relative timestamps stay fresh. */
export function useNow(ms = 15_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}
