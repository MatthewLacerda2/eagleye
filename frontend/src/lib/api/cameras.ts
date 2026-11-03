import { request } from "@/lib/api/client";
import type { CameraStatus, EventTypeRead } from "@/lib/schemas/cameras";

/** The typed cameras and catalog SDK. */

export function listCameras(): Promise<CameraStatus[]> {
  return request<CameraStatus[]>("/cameras");
}

export function listEventTypes(): Promise<EventTypeRead[]> {
  return request<EventTypeRead[]>("/catalog");
}

export function cameraFramePath(id: string): string {
  return `/cameras/${id}/frame`;
}
