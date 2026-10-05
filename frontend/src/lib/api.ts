import type {
  Album,
  Facets,
  JobPage,
  PhotoDetail,
  PhotoPage,
  PhotoUpdate,
  Stats,
  SystemEvent,
  SystemOverview,
  Tag,
} from "./types";

// All requests are same-origin; the Next.js server proxies /api/* to the
// backend container, so no host/IP is ever baked into the browser bundle.
const BASE = "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, detail || `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export type PhotoQuery = Record<string, string | number | boolean | undefined | null>;

export function toSearchParams(query: PhotoQuery): URLSearchParams {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "" || v === false) continue;
    params.set(k, String(v));
  }
  return params;
}

export const api = {
  photos: (query: PhotoQuery) => request<PhotoPage>(`/photos?${toSearchParams(query)}`),
  photo: (id: string) => request<PhotoDetail>(`/photos/${id}`),
  facets: () => request<Facets>("/photos/facets"),
  updatePhoto: (id: string, body: PhotoUpdate) =>
    request<PhotoDetail>(`/photos/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  bulkUpdate: (ids: string[], body: PhotoUpdate) =>
    request<{ updated: number }>("/photos/bulk", { method: "POST", body: JSON.stringify({ ids, ...body }) }),
  analyze: (
    id: string,
    body: { technical?: boolean; ai?: boolean; provider?: string; rerender?: boolean } = {},
  ) => request<{ queued: string[] }>(`/photos/${id}/analyze`, { method: "POST", body: JSON.stringify(body) }),
  linkImmich: (id: string) => request<PhotoDetail>(`/photos/${id}/immich/link`, { method: "POST" }),
  stats: () => request<Stats>("/stats"),
  system: () => request<SystemOverview>("/system"),
  rescan: () =>
    request<{ queued: boolean; job_id: string | null; detail: string | null }>("/system/rescan", {
      method: "POST",
    }),
  verify: () => request<{ queued: boolean }>("/system/verify", { method: "POST" }),
  jobs: (query: PhotoQuery = {}) => request<JobPage>(`/jobs?${toSearchParams(query)}`),
  retryJob: (id: string) => request<{ job_id: string | null }>(`/jobs/${id}/retry`, { method: "POST" }),
  retryFailed: () => request<{ queued: number }>("/jobs/retry-failed", { method: "POST" }),
  events: (query: PhotoQuery = {}) => request<SystemEvent[]>(`/events?${toSearchParams(query)}`),
  albums: () => request<Album[]>("/albums"),
  tags: () => request<Tag[]>("/tags"),
};

export const EVENTS_URL = `${BASE}/events/stream`;
