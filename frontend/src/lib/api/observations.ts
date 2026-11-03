import { request } from "@/lib/api/client";
import type {
  ObservationDetail,
  ObservationFilters,
  ObservationRead,
  ReviewWrite,
} from "@/lib/schemas/observations";

/** The typed observations SDK — one function per backend `/observations` endpoint. */

export const PAGE_SIZE = 50;

export function listObservations(
  filters: ObservationFilters,
): Promise<ObservationRead[]> {
  const params = new URLSearchParams({
    only_events: String(filters.only_events),
    unreviewed: String(filters.unreviewed),
    limit: String(PAGE_SIZE),
  });
  if (filters.site) params.set("site", filters.site);
  if (filters.event) params.set("event", filters.event);
  if (filters.before) params.set("before", filters.before);
  return request<ObservationRead[]>(`/observations?${params.toString()}`);
}

export function getObservation(id: string): Promise<ObservationDetail> {
  return request<ObservationDetail>(`/observations/${id}`);
}

export function reviewObservation(
  id: string,
  payload: ReviewWrite,
): Promise<ObservationRead> {
  return request<ObservationRead>(`/observations/${id}/review`, {
    method: "PUT",
    body: payload,
  });
}

export function observationFramePath(id: string): string {
  return `/observations/${id}/frame`;
}
