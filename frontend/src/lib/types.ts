// Mirrors backend/app/schemas/*.py. Keep in sync with the API.

export type Flag = "none" | "pick" | "reject";

export interface PhotoSummary {
  id: string;
  base_filename: string;
  media_type: "still" | "video";
  capture_time: string | null;
  imported_at: string;
  camera: string | null;
  lens_model: string | null;
  focal_length: number | null;
  aperture: number | null;
  shutter_speed: number | null;
  iso: number | null;
  exposure_compensation: number | null;
  rating: number;
  flag: Flag;
  rejected: boolean;
  picked: boolean;
  favorite: boolean;
  needs_edit: boolean;
  exported: boolean;
  has_jpeg: boolean;
  has_raw: boolean;
  has_video: boolean;
  processing_status: "pending" | "ready" | "error";
  scene: string | null;
  burst_group_id: string | null;
  burst_index: number | null;
  burst_size: number | null;
  thumb_url: string | null;
  thumb_width: number | null;
  thumb_height: number | null;
  sharpness_score: number | null;
  exposure_label: string | null;
  face_count: number | null;
}

export interface PhotoPage {
  items: PhotoSummary[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export type BestPeriod = "session" | "today" | "7d" | "all";

export interface BestPhoto {
  photo: PhotoSummary;
  /** 0–100 blend of AI aesthetic, measured sharpness and eye focus. */
  score: number;
  /** 0–10 AI estimate; null when no vision model has scored the frame. */
  aesthetic_score: number | null;
  eye_sharpness: number | null;
}

export interface BestPhotos {
  period: BestPeriod;
  period_start: string | null;
  candidates: number;
  ai_scored: number;
  items: BestPhoto[];
}

export interface PhotoFile {
  id: string;
  file_type: "jpeg" | "image" | "raw" | "video";
  filename: string;
  extension: string;
  mime_type: string | null;
  file_size: number;
  checksum: string | null;
  modification_time: string;
  width: number | null;
  height: number | null;
  exists: boolean;
  is_duplicate: boolean;
  container_path: string;
  nas_path: string;
  smb_path: string | null;
  relative_path: string;
  download_url: string;
}

/** Normalised (0..1) coordinates relative to the analysed image. */
export interface Face {
  x: number;
  y: number;
  w: number;
  h: number;
  confidence: number;
  sharpness: number | null;
  eyes: { x: number; y: number; sharpness: number | null }[];
}

export interface Analysis {
  sharpness_score: number | null;
  sharpness_label: string | null;
  sharpness_global: number | null;
  sharpness_peak: number | null;
  blur_score: number | null;
  is_blurry: boolean | null;
  brightness: number | null;
  contrast: number | null;
  saturation: number | null;
  dynamic_range_ev: number | null;
  highlight_clipping_percent: number | null;
  shadow_clipping_percent: number | null;
  exposure_label: string | null;
  exposure_assessment: string | null;
  histogram: Partial<Record<"r" | "g" | "b" | "l", number[]>>;
  dominant_colors: { hex: string; fraction: number }[];
  face_count: number | null;
  eye_count: number | null;
  faces: Face[];
  subject_detected: boolean | null;
  warnings: string[];
  source: string | null;
  algorithm_version: string;
  duration_ms: number | null;
  analyzed_at: string;
}

export interface Critique {
  id: string;
  provider: string;
  model_name: string | null;
  status: "succeeded" | "failed" | string;
  scene: string | null;
  subject: string | null;
  description: string | null;
  composition: string[];
  technical: string[];
  issues: string[];
  suggestions: string[];
  tags: string[];
  aesthetic_score: number | null;
  confidence: number | null;
  error: string | null;
  duration_ms: number | null;
  created_at: string;
}

export interface Tag {
  id: number;
  name: string;
  color?: string | null;
  count?: number | null;
}

export interface Burst {
  id: string;
  photo_count: number;
  start_time: string;
  end_time: string;
  cover_photo_id: string | null;
  members: PhotoSummary[];
}

export interface PhotoDetail extends PhotoSummary {
  camera_make: string | null;
  camera_model: string | null;
  camera_serial: string | null;
  shutter_count: number | null;
  firmware: string | null;
  capture_tz_offset: string | null;
  focal_length_35mm: number | null;
  exposure_program: string | null;
  metering_mode: string | null;
  white_balance: string | null;
  flash: string | null;
  focus_mode: string | null;
  af_area_mode: string | null;
  picture_control: string | null;
  image_quality: string | null;
  image_width: number | null;
  image_height: number | null;
  orientation: number | null;
  color_space: string | null;
  duration_seconds: number | null;
  gps_latitude: number | null;
  gps_longitude: number | null;
  gps_altitude: number | null;
  extra: Record<string, unknown>;
  notes: string | null;
  processing_error: string | null;
  preview_url: string | null;
  preview_width: number | null;
  preview_height: number | null;
  files: PhotoFile[];
  analysis: Analysis | null;
  critique: Critique | null;
  critique_history: number;
  tags: Tag[];
  albums: { id: string; name: string }[];
  burst: Burst | null;
  immich_asset_id: string | null;
  immich_url: string | null;
  immich_enabled: boolean;
  prev_id: string | null;
  next_id: string | null;
}

export interface PhotoUpdate {
  rating?: number;
  flag?: Flag;
  favorite?: boolean;
  needs_edit?: boolean;
  exported?: boolean;
  notes?: string;
  tags?: string[];
}

export interface Facets {
  cameras: string[];
  lenses: string[];
  scenes: string[];
  tags: string[];
  iso_range: [number | null, number | null];
  focal_range: [number | null, number | null];
  aperture_range: [number | null, number | null];
  date_range: [string | null, string | null];
}

export interface CameraStatus {
  state: "receiving" | "idle" | "never";
  last_upload_at: string | null;
  session_started_at: string | null;
  session_files: number;
  session_photos: number;
  session_bytes: number;
  camera: string | null;
}

export interface Stats {
  camera: CameraStatus;
  today: {
    photos: number;
    raw_files: number;
    jpeg_files: number;
    videos: number;
    bytes: number;
    picks: number;
    rejects: number;
  };
  totals: {
    photos: number;
    raw_files: number;
    jpeg_files: number;
    videos: number;
    bytes: number;
    favorites: number;
    rejected: number;
    pending: number;
    errors: number;
  };
  latest_photo_id: string | null;
  recent: PhotoSummary[];
}

export interface ComponentHealth {
  ok: boolean;
  detail?: string | null;
  data?: Record<string, unknown>;
}

export interface DiskUsage {
  path: string;
  total: number;
  used: number;
  free: number;
}

export interface RootStatus {
  name: string;
  path: string;
  nas_path: string;
  accessible: boolean;
  required: boolean;
  writable: boolean;
}

export interface SystemOverview {
  time: string;
  version: string;
  components: Record<string, ComponentHealth>;
  queues: { name: string; queued: number; started: number; scheduled: number; failed: number }[];
  jobs: { pending: number; failed: number; succeeded: number; by_status: Record<string, number> };
  last_successful_ingest: string | null;
  last_new_photo: string | null;
  disk: { photos: DiskUsage | null; data: DiskUsage | null };
  cache: { bytes: number; files: number };
  config: {
    ai_provider: string;
    ai_auto_analyze: boolean;
    ai_providers: { name: string; configured: boolean; active: boolean; model?: string | null }[];
    watch_mode: string;
    file_stable_seconds: number;
    pair_window_seconds: number;
    reconcile_interval_minutes: number;
    immich_enabled: boolean;
    immich_reachable: boolean | null;
    immich_detail: string | null;
    auth_enabled: boolean;
    nas_photo_root: string;
  };
  versions: { app: string; exiftool: string | null };
}

export interface Job {
  id: string;
  kind: string;
  status: "queued" | "running" | "succeeded" | "failed" | "retried";
  queue: string;
  photo_id: string | null;
  target_path: string | null;
  payload: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error: string | null;
  attempts: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
}

export interface JobPage {
  items: Job[];
  total: number;
  counts: Record<string, number>;
}

export interface SystemEvent {
  id: number;
  created_at: string;
  level: "info" | "warning" | "error" | string;
  category: string;
  event: string;
  message: string;
  photo_id: string | null;
  data: Record<string, unknown>;
}

export interface Album {
  id: string;
  name: string;
  description: string | null;
  photo_count: number;
  cover_thumb_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface LiveMessage {
  type: "photo.created" | "photo.updated" | "photo.analyzed" | "system.event" | "job.updated" | string;
  ts: string;
  data: Record<string, unknown>;
}
