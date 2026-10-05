"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  CheckCircle2,
  Cpu,
  Database,
  FolderSearch,
  HardDrive,
  ListChecks,
  RefreshCw,
  RotateCcw,
  ScrollText,
  Settings2,
  XCircle,
} from "lucide-react";
import { useState } from "react";
import { ActivityFeed } from "@/components/activity-feed";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { api } from "@/lib/api";
import { formatBytes, formatDateTime, formatRelative, titleCase } from "@/lib/format";
import { useNow } from "@/lib/hooks";
import type { ComponentHealth, DiskUsage, Job, RootStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const COMPONENT_LABEL: Record<string, string> = {
  api: "API",
  database: "PostgreSQL",
  redis: "Redis",
  worker: "Workers",
  watcher: "File watcher",
  photo_roots: "Photo folders",
};

function HealthTile({ name, c }: { name: string; c: ComponentHealth }) {
  return (
    <div
      className={cn(
        "flex items-start gap-2.5 rounded-lg border px-3 py-2.5",
        c.ok ? "border-ink-800 bg-ink-900/80" : "border-bad/30 bg-bad/5",
      )}
      data-testid={`health-${name}`}
    >
      {c.ok ? (
        <CheckCircle2 className="text-ok mt-0.5 size-4" />
      ) : (
        <XCircle className="text-bad mt-0.5 size-4" />
      )}
      <div className="min-w-0">
        <div className="text-sm font-medium">{COMPONENT_LABEL[name] ?? titleCase(name)}</div>
        <div className="text-ink-400 truncate text-[11px]" title={c.detail ?? ""}>
          {c.detail ?? (c.ok ? "Healthy" : "Unavailable")}
        </div>
      </div>
    </div>
  );
}

function DiskBar({ label, disk }: { label: string; disk: DiskUsage | null }) {
  if (!disk) return <div className="text-ink-500 text-sm">{label}: unavailable</div>;
  const pct = (disk.used / disk.total) * 100;
  return (
    <div>
      <div className="mb-1 flex justify-between text-[12px]">
        <span className="text-ink-300">{label}</span>
        <span className="text-ink-400 tabular">
          {formatBytes(disk.free)} free of {formatBytes(disk.total)}
        </span>
      </div>
      <div className="bg-ink-800 h-2 overflow-hidden rounded-full">
        <div
          className={cn("h-full rounded-full", pct > 90 ? "bg-bad" : pct > 75 ? "bg-warn" : "bg-ok")}
          style={{ width: `${pct}%` }}
        />
      </div>
      <code className="text-ink-500 mt-1 block truncate font-mono text-[10px]">{disk.path}</code>
    </div>
  );
}

const STATUS_TONE: Record<Job["status"], "neutral" | "info" | "ok" | "bad"> = {
  queued: "neutral",
  running: "info",
  succeeded: "ok",
  failed: "bad",
  retried: "neutral",
};

function JobsTable() {
  const qc = useQueryClient();
  const toast = useToast();
  const now = useNow();
  const [status, setStatus] = useState("");
  const jobs = useQuery({
    queryKey: ["jobs", status],
    queryFn: () => api.jobs({ status, limit: 50 }),
    refetchInterval: 10_000,
  });
  const retry = useMutation({
    mutationFn: api.retryJob,
    onSuccess: () => {
      toast("Job re-queued", "ok");
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e) => toast(e instanceof Error ? e.message : "Retry failed", "error"),
  });
  const retryAll = useMutation({
    mutationFn: api.retryFailed,
    onSuccess: (r) => {
      toast(`Re-queued ${r.queued} failed job(s)`, "ok");
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e) => toast(e instanceof Error ? e.message : "Retry failed", "error"),
  });
  const counts = jobs.data?.counts ?? {};

  return (
    <Card>
      <CardHeader
        title="Jobs"
        icon={<ListChecks className="size-3.5" />}
        action={
          <div className="flex items-center gap-2">
            <Select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="h-7 w-32 text-xs"
              aria-label="Job status"
            >
              <option value="">All ({Object.values(counts).reduce((a, b) => a + b, 0)})</option>
              {["queued", "running", "succeeded", "failed", "retried"].map((s) => (
                <option key={s} value={s}>
                  {titleCase(s)} ({counts[s] ?? 0})
                </option>
              ))}
            </Select>
            <Button
              size="sm"
              variant="outline"
              disabled={!counts.failed || retryAll.isPending}
              onClick={() => retryAll.mutate()}
            >
              <RotateCcw className="size-3.5" /> Retry failed
            </Button>
          </div>
        }
      />
      <CardBody className="overflow-x-auto">
        {jobs.isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : !jobs.data?.items.length ? (
          <p className="text-ink-500 text-sm">No jobs.</p>
        ) : (
          <table className="w-full text-left text-[12px]" data-testid="jobs-table">
            <thead className="text-ink-500 text-[10px] tracking-wider uppercase">
              <tr>
                <th className="py-1.5 pr-3 font-semibold">Kind</th>
                <th className="py-1.5 pr-3 font-semibold">Status</th>
                <th className="py-1.5 pr-3 font-semibold">Target</th>
                <th className="py-1.5 pr-3 font-semibold">Tries</th>
                <th className="py-1.5 pr-3 font-semibold">Took</th>
                <th className="py-1.5 pr-3 font-semibold">When</th>
                <th />
              </tr>
            </thead>
            <tbody className="divide-ink-800 divide-y">
              {jobs.data.items.map((j) => (
                <tr key={j.id} className="align-top">
                  <td className="text-ink-200 py-1.5 pr-3 font-mono">{j.kind}</td>
                  <td className="py-1.5 pr-3">
                    <Badge tone={STATUS_TONE[j.status]}>{j.status}</Badge>
                  </td>
                  <td className="max-w-md py-1.5 pr-3">
                    <div className="text-ink-300 truncate font-mono" title={j.target_path ?? ""}>
                      {j.target_path?.split("/").slice(-1)[0] ?? j.photo_id?.slice(0, 8) ?? "—"}
                    </div>
                    {j.error && (
                      <div className="text-bad/90 line-clamp-2" title={j.error}>
                        {j.error.split("\n")[0]}
                      </div>
                    )}
                  </td>
                  <td className="tabular py-1.5 pr-3">{j.attempts}</td>
                  <td className="tabular py-1.5 pr-3">
                    {j.duration_ms != null ? `${j.duration_ms} ms` : "—"}
                  </td>
                  <td className="text-ink-400 py-1.5 pr-3 whitespace-nowrap">
                    {formatRelative(j.created_at, now)}
                  </td>
                  <td className="py-1.5 text-right">
                    {j.status === "failed" && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => retry.mutate(j.id)}
                        disabled={retry.isPending}
                      >
                        Retry
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardBody>
    </Card>
  );
}

export default function SystemPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const now = useNow();
  const sys = useQuery({ queryKey: ["system"], queryFn: api.system, refetchInterval: 15_000 });

  const rescan = useMutation({
    mutationFn: api.rescan,
    onSuccess: (r) => {
      toast(
        r.queued
          ? "Rescan queued — existing photos are not duplicated"
          : (r.detail ?? "Scan already running"),
        r.queued ? "ok" : "info",
      );
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e) => toast(e instanceof Error ? e.message : "Rescan failed", "error"),
  });
  const verify = useMutation({
    mutationFn: api.verify,
    onSuccess: (r) => toast(r.queued ? "File verification queued" : "Verification already running", "ok"),
    onError: (e) => toast(e instanceof Error ? e.message : "Verify failed", "error"),
  });

  const s = sys.data;
  const aiModel = s?.config.ai_providers.find((p) => p.active)?.model;
  const roots = (s?.components.photo_roots?.data?.roots ?? []) as RootStatus[];
  const workers = (s?.components.worker?.data?.workers ?? []) as {
    name: string;
    state: string;
    queues: string[];
  }[];

  return (
    <div className="mx-auto max-w-[1600px] space-y-5 p-4 md:p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">System</h1>
          <p className="text-ink-400 text-sm">
            {s
              ? `v${s.version} · ExifTool ${s.versions.exiftool ?? "not found"} · updated ${formatRelative(s.time, now)}`
              : "Loading…"}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => verify.mutate()} disabled={verify.isPending}>
            <FolderSearch className="size-4" /> Verify files
          </Button>
          <Button variant="primary" onClick={() => rescan.mutate()} disabled={rescan.isPending}>
            <RefreshCw className={cn("size-4", rescan.isPending && "animate-spin")} /> Rescan library
          </Button>
        </div>
      </div>

      {sys.isError && (
        <div className="border-bad/30 bg-bad/5 text-bad rounded-lg border p-3 text-sm">
          Backend unreachable: {sys.error instanceof Error ? sys.error.message : "unknown error"}
        </div>
      )}

      <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {s
          ? Object.entries(s.components).map(([name, c]) => <HealthTile key={name} name={name} c={c} />)
          : Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-14" />)}
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <Card>
          <CardHeader title="Pipeline" icon={<Cpu className="size-3.5" />} />
          <CardBody className="space-y-3 text-[13px]">
            <dl className="grid grid-cols-2 gap-y-1.5">
              <dt className="text-ink-400">Last ingest</dt>
              <dd className="tabular text-right">{formatRelative(s?.last_successful_ingest, now)}</dd>
              <dt className="text-ink-400">Last new photo</dt>
              <dd className="tabular text-right">{formatRelative(s?.last_new_photo, now)}</dd>
              <dt className="text-ink-400">Pending jobs</dt>
              <dd className="tabular text-right">{s?.jobs.pending ?? "—"}</dd>
              <dt className="text-ink-400">Failed jobs</dt>
              <dd className={cn("tabular text-right", s?.jobs.failed ? "text-bad" : "")}>
                {s?.jobs.failed ?? "—"}
              </dd>
            </dl>
            <table className="w-full text-[12px]">
              <thead className="text-ink-500 text-[10px] tracking-wider uppercase">
                <tr>
                  <th className="text-left font-semibold">Queue</th>
                  <th className="text-right font-semibold">Waiting</th>
                  <th className="text-right font-semibold">Running</th>
                  <th className="text-right font-semibold">Failed</th>
                </tr>
              </thead>
              <tbody>
                {s?.queues.map((q) => (
                  <tr key={q.name}>
                    <td className="py-0.5 font-mono">{q.name}</td>
                    <td className="tabular text-right">{q.queued}</td>
                    <td className="tabular text-right">{q.started}</td>
                    <td className={cn("tabular text-right", q.failed && "text-bad")}>{q.failed}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {workers.length > 0 && (
              <ul className="text-ink-400 space-y-0.5 text-[11px]">
                {workers.map((w) => (
                  <li key={w.name} className="truncate font-mono">
                    {w.name} · {w.state} · {w.queues?.join(", ")}
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Storage" icon={<HardDrive className="size-3.5" />} />
          <CardBody className="space-y-4">
            <DiskBar
              label={roots.some((r) => r.writable) ? "Photos (mount is writable)" : "Photos (read-only)"}
              disk={s?.disk.photos ?? null}
            />
            <DiskBar label="App data" disk={s?.disk.data ?? null} />
            <div className="flex justify-between text-[12px]">
              <span className="text-ink-400">Preview / thumbnail cache</span>
              <span className="tabular">
                {formatBytes(s?.cache.bytes ?? 0)} · {s?.cache.files ?? 0} files
              </span>
            </div>
            <ul className="space-y-1">
              {roots.map((r) => (
                <li key={r.name} className="flex items-center gap-2 text-[12px]">
                  <span
                    className={cn(
                      "size-1.5 rounded-full",
                      r.accessible ? "bg-ok" : r.required ? "bg-bad" : "bg-ink-600",
                    )}
                    title={r.accessible ? "accessible" : r.required ? "unavailable" : "optional, not present"}
                  />
                  <span className="text-ink-300 w-16 font-mono">{r.name}</span>
                  <code
                    className="text-ink-500 min-w-0 flex-1 truncate font-mono text-[11px]"
                    title={r.nas_path}
                  >
                    {r.nas_path}
                  </code>
                  <Badge tone={r.writable ? "warn" : "ok"}>{r.writable ? "writable" : "read-only"}</Badge>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Configuration" icon={<Settings2 className="size-3.5" />} />
          <CardBody>
            {s && (
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[13px]">
                <dt className="text-ink-400">AI provider</dt>
                <dd className="text-right">
                  {s.config.ai_provider}
                  {aiModel && <span className="text-ink-400"> · {aiModel}</span>}
                  {s.config.ai_auto_analyze ? " · auto" : " · manual"}
                </dd>
                <dt className="text-ink-400">Providers</dt>
                <dd className="flex flex-wrap justify-end gap-1">
                  {s.config.ai_providers.map((p) => (
                    <Badge key={p.name} tone={p.active ? "accent" : p.configured ? "ok" : "neutral"}>
                      {p.name}
                    </Badge>
                  ))}
                </dd>
                <dt className="text-ink-400">Watch mode</dt>
                <dd className="text-right">{s.config.watch_mode}</dd>
                <dt className="text-ink-400">Stable after</dt>
                <dd className="text-right">{s.config.file_stable_seconds}s</dd>
                <dt className="text-ink-400">Pair window</dt>
                <dd className="text-right">±{s.config.pair_window_seconds}s</dd>
                <dt className="text-ink-400">Reconcile</dt>
                <dd className="text-right">every {s.config.reconcile_interval_minutes} min</dd>
                <dt className="text-ink-400">Immich</dt>
                <dd className="text-right">
                  {!s.config.immich_enabled
                    ? "disabled"
                    : s.config.immich_reachable
                      ? "connected (read-only)"
                      : `unreachable${s.config.immich_detail ? `: ${s.config.immich_detail}` : ""}`}
                </dd>
                <dt className="text-ink-400">API token</dt>
                <dd className="text-right">{s.config.auth_enabled ? "enabled" : "off (LAN only)"}</dd>
              </dl>
            )}
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        <JobsTable />
        <Card>
          <CardHeader title="Event log" icon={<ScrollText className="size-3.5" />} />
          <CardBody className="max-h-[32rem] overflow-y-auto">
            <ActivityFeed limit={60} />
          </CardBody>
        </Card>
      </div>

      <p className="text-ink-500 flex items-center gap-2 text-[11px]">
        <Database className="size-3" /> Originals are never modified; ratings, flags and tags live in
        PostgreSQL only.
        <Activity className="ml-2 size-3" /> Prometheus metrics at <code className="font-mono">/metrics</code>{" "}
        on the backend port. Server time {formatDateTime(s?.time)}.
      </p>
    </div>
  );
}
