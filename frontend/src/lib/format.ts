const DASH = "—";

export function formatShutter(seconds: number | null | undefined): string {
  if (seconds == null || seconds <= 0) return DASH;
  if (seconds >= 0.3) {
    const rounded = Math.round(seconds * 10) / 10;
    return `${Number.isInteger(rounded) ? rounded.toFixed(0) : rounded}"`;
  }
  return `1/${Math.round(1 / seconds)}`;
}

export function formatAperture(f: number | null | undefined): string {
  if (f == null) return DASH;
  return `f/${Number.isInteger(f) ? f.toFixed(0) : f.toFixed(1).replace(/\.0$/, "")}`;
}

export function formatFocal(mm: number | null | undefined): string {
  if (mm == null) return DASH;
  return `${Math.round(mm)}mm`;
}

export function formatIso(iso: number | null | undefined): string {
  return iso == null ? DASH : `ISO ${iso}`;
}

/** Exposure compensation in photographer thirds: +1/3, -1 2/3, 0. */
export function formatEv(ev: number | null | undefined): string {
  if (ev == null) return DASH;
  const thirds = Math.round(ev * 3);
  if (thirds === 0) return "0 EV";
  const sign = thirds > 0 ? "+" : "−";
  const abs = Math.abs(thirds);
  const whole = Math.floor(abs / 3);
  const rem = abs % 3;
  const frac = rem ? `${rem}/3` : "";
  const body = whole && frac ? `${whole} ${frac}` : whole ? `${whole}` : frac;
  return `${sign}${body} EV`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return DASH;
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return `${value.toFixed(value >= 100 || i === 0 ? 0 : 1)} ${units[i]}`;
}

export function formatDateTime(iso: string | null | undefined, opts?: Intl.DateTimeFormatOptions): string {
  if (!iso) return DASH;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return DASH;
  return d.toLocaleString(undefined, opts ?? { dateStyle: "medium", timeStyle: "medium" });
}

export function formatTime(iso: string | null | undefined): string {
  return formatDateTime(iso, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function formatRelative(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "never";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "never";
  const s = Math.round((now - t) / 1000);
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.round(h / 24);
  return `${d} d ago`;
}

export function exposureLine(p: {
  focal_length: number | null;
  aperture: number | null;
  shutter_speed: number | null;
  iso: number | null;
}): string {
  return [
    formatFocal(p.focal_length),
    formatAperture(p.aperture),
    formatShutter(p.shutter_speed),
    formatIso(p.iso),
  ]
    .filter((s) => s !== DASH)
    .join(" · ");
}

export function percent(value: number | null | undefined, digits = 1): string {
  return value == null ? DASH : `${value.toFixed(digits)}%`;
}

export function titleCase(s: string | null | undefined): string {
  if (!s) return DASH;
  return s.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
