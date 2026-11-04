/** Mirrors backend `schemas/cameras.py`. Keep in sync with the Pydantic models. */

export interface CameraStatus {
  id: string;
  site_key: string;
  site_name: string;
  key: string;
  label: string;
  enabled: boolean;
  status: "unknown" | "online" | "offline";
  last_capture_at: string | null;
  last_sent_at: string | null;
  has_frame: boolean;
}

export interface EventTypeRead {
  key: string;
  name: string;
  severity: "info" | "warning" | "critical";
  alert: boolean;
}
