"use client";

import { Camera, Radio } from "lucide-react";
import { formatBytes, formatRelative } from "@/lib/format";
import { useNow } from "@/lib/hooks";
import type { CameraStatus as CameraStatusT } from "@/lib/types";
import { cn } from "@/lib/utils";

const COPY = {
  receiving: { label: "Receiving", sub: "Camera is uploading over FTP" },
  idle: { label: "Idle", sub: "No uploads in the last few minutes" },
  never: { label: "Waiting", sub: "No uploads recorded yet" },
} as const;

export function CameraStatusCard({ status }: { status: CameraStatusT | undefined }) {
  const now = useNow(5_000);
  const state = status?.state ?? "never";
  const copy = COPY[state];
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl border p-4",
        state === "receiving" ? "border-ok/30 bg-ok/[0.04]" : "border-ink-800 bg-ink-900/80",
      )}
      data-testid="camera-status"
    >
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "grid size-10 place-items-center rounded-lg",
            state === "receiving" ? "bg-ok/15 text-ok" : "bg-ink-800 text-ink-400",
          )}
        >
          {state === "receiving" ? <Radio className="size-5" /> : <Camera className="size-5" />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-semibold">{status?.camera ?? "Nikon Z6III"}</span>
            <span
              className={cn(
                "flex items-center gap-1.5 text-xs",
                state === "receiving" ? "text-ok" : "text-ink-400",
              )}
            >
              <span
                className={cn(
                  "size-1.5 rounded-full",
                  state === "receiving" ? "pulse-ring bg-ok" : "bg-ink-500",
                )}
              />
              {copy.label}
            </span>
          </div>
          <p className="text-ink-400 text-xs">{copy.sub}</p>
        </div>
      </div>
      <dl className="mt-4 grid grid-cols-3 gap-2 text-center">
        <div>
          <dt className="text-ink-500 text-[10px] tracking-wider uppercase">Last upload</dt>
          <dd className="tabular text-sm">{formatRelative(status?.last_upload_at, now)}</dd>
        </div>
        <div>
          <dt className="text-ink-500 text-[10px] tracking-wider uppercase">Session</dt>
          <dd className="tabular text-sm">{status?.session_photos ?? 0} photos</dd>
        </div>
        <div>
          <dt className="text-ink-500 text-[10px] tracking-wider uppercase">Transferred</dt>
          <dd className="tabular text-sm">{formatBytes(status?.session_bytes ?? 0)}</dd>
        </div>
      </dl>
    </div>
  );
}
