import {
  formatAperture,
  formatDateTime,
  formatEv,
  formatFocal,
  formatShutter,
  titleCase,
} from "@/lib/format";
import type { PhotoDetail } from "@/lib/types";
import { cn } from "@/lib/utils";

type Row = [label: string, value: string | number | null | undefined];

function Section({ title, rows }: { title: string; rows: Row[] }) {
  const visible = rows.filter(([, v]) => v !== null && v !== undefined && v !== "" && v !== "—");
  if (!visible.length) return null;
  return (
    <div>
      <h4 className="text-ink-200 mb-1.5 text-sm font-semibold">{title}</h4>
      <dl className="grid grid-cols-[minmax(7rem,auto)_1fr] gap-x-4 gap-y-1 text-[13px]">
        {visible.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-ink-400">{label}</dt>
            <dd className="text-ink-100 tabular truncate" title={String(value)}>
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/** Big four exposure values, camera-LCD style. */
export function ExposureStrip({ photo, className }: { photo: PhotoDetail; className?: string }) {
  const cells: [string, string][] = [
    ["Shutter", formatShutter(photo.shutter_speed)],
    ["Aperture", formatAperture(photo.aperture)],
    ["ISO", photo.iso != null ? String(photo.iso) : "—"],
    ["Focal", formatFocal(photo.focal_length)],
    ["Exp. comp", formatEv(photo.exposure_compensation)],
  ];
  return (
    <div
      className={cn(
        "divide-ink-800 border-ink-800 bg-ink-950/60 grid grid-cols-5 divide-x rounded-lg border",
        className,
      )}
    >
      {cells.map(([label, value]) => (
        <div key={label} className="px-2 py-2 text-center">
          <div className="text-ink-300 text-xs">{label}</div>
          <div className="text-ink-100 tabular mt-0.5 font-mono text-[15px]">{value}</div>
        </div>
      ))}
    </div>
  );
}

export function MetadataGrid({ photo }: { photo: PhotoDetail }) {
  const extra = photo.extra ?? {};
  const extraRows: Row[] = Object.entries(extra)
    .filter(([, v]) => v !== null && typeof v !== "object")
    .map(([k, v]) => [titleCase(k), String(v)]);
  const gps =
    photo.gps_latitude != null && photo.gps_longitude != null
      ? `${photo.gps_latitude.toFixed(5)}, ${photo.gps_longitude.toFixed(5)}`
      : null;

  return (
    <div className="space-y-4" data-testid="metadata-grid">
      <Section
        title="Capture"
        rows={[
          ["Captured", formatDateTime(photo.capture_time)],
          ["Time zone", photo.capture_tz_offset],
          ["Imported", formatDateTime(photo.imported_at)],
          [
            "Dimensions",
            photo.image_width && photo.image_height ? `${photo.image_width} × ${photo.image_height}` : null,
          ],
          ["Duration", photo.duration_seconds ? `${photo.duration_seconds.toFixed(1)} s` : null],
          ["GPS", gps],
        ]}
      />
      <Section
        title="Camera"
        rows={[
          ["Body", photo.camera],
          ["Serial", photo.camera_serial],
          ["Shutter count", photo.shutter_count],
          ["Firmware", photo.firmware],
          ["Quality", photo.image_quality],
          ["Color space", photo.color_space],
        ]}
      />
      <Section
        title="Lens & exposure"
        rows={[
          ["Lens", photo.lens_model],
          ["Focal length", formatFocal(photo.focal_length)],
          ["35mm equiv.", photo.focal_length_35mm ? formatFocal(photo.focal_length_35mm) : null],
          ["Program", photo.exposure_program],
          ["Metering", photo.metering_mode],
          ["Flash", photo.flash],
        ]}
      />
      <Section
        title="Focus & color"
        rows={[
          ["Focus mode", photo.focus_mode],
          ["AF area", photo.af_area_mode],
          ["White balance", photo.white_balance],
          ["Picture Control", photo.picture_control],
        ]}
      />
      <Section title="Nikon" rows={extraRows} />
    </div>
  );
}
