"use client";

import { AlertTriangle, Copy, Download, FileImage, FileVideo, HardDrive } from "lucide-react";
import { formatBytes, formatDateTime } from "@/lib/format";
import { useCopy } from "@/lib/hooks";
import type { PhotoFile } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge } from "./ui/badge";
import { buttonClass } from "./ui/button";

const LABEL: Record<PhotoFile["file_type"], string> = {
  jpeg: "JPEG",
  image: "Image",
  raw: "RAW",
  video: "Video",
};

function PathRow({ label, value }: { label: string; value: string }) {
  const copy = useCopy();
  return (
    <div className="group flex items-center gap-2">
      <span className="text-ink-300 w-10 shrink-0 text-xs font-semibold">{label}</span>
      <code className="text-ink-300 min-w-0 flex-1 truncate font-mono text-xs" title={value}>
        {value}
      </code>
      <button
        type="button"
        onClick={() => copy(value, `${label} path`)}
        className="text-ink-400 hover:bg-ink-800 hover:text-ink-100 rounded p-1"
        aria-label={`Copy ${label} path`}
      >
        <Copy className="size-3.5" />
      </button>
    </div>
  );
}

export function FilesPanel({ files }: { files: PhotoFile[] }) {
  if (!files.length) return <p className="text-ink-400 text-sm">No files.</p>;
  const ordered = [...files].sort((a, b) => Number(a.is_duplicate) - Number(b.is_duplicate));
  return (
    <ul className="space-y-3" data-testid="files-panel">
      {ordered.map((f) => {
        const Icon = f.file_type === "video" ? FileVideo : f.file_type === "raw" ? HardDrive : FileImage;
        return (
          <li
            key={f.id}
            className={cn("border-ink-800 bg-ink-950/50 rounded-lg border p-3", !f.exists && "opacity-60")}
          >
            <div className="mb-2 flex items-center gap-2">
              <Icon className={cn("size-4", f.file_type === "raw" ? "text-accent" : "text-ink-300")} />
              <span className="text-ink-100 font-mono text-sm">{f.filename}</span>
              <Badge tone={f.file_type === "raw" ? "accent" : "neutral"}>{LABEL[f.file_type]}</Badge>
              {f.is_duplicate && <Badge tone="warn">Duplicate</Badge>}
              {!f.exists && (
                <Badge tone="bad">
                  <AlertTriangle className="size-3" /> Missing
                </Badge>
              )}
              <span className="text-ink-400 tabular ml-auto text-xs">{formatBytes(f.file_size)}</span>
            </div>
            <div className="space-y-1">
              <PathRow label="NAS" value={f.nas_path} />
              {f.smb_path && <PathRow label="SMB" value={f.smb_path} />}
            </div>
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="text-ink-400 text-xs">
                {f.width && f.height ? `${f.width}×${f.height} · ` : ""}modified{" "}
                {formatDateTime(f.modification_time)}
              </span>
              {f.exists && (
                <a
                  href={f.download_url}
                  download={f.filename}
                  className={buttonClass({ size: "sm", variant: "outline" })}
                >
                  <Download className="size-3.5" /> Download {LABEL[f.file_type]}
                </a>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
