/** Mirrors backend `schemas/observations.py`. Keep in sync with the Pydantic models. */

export type Review = "correct" | "incorrect";

export interface ObservationRead {
  id: string;
  analysis_id: string;
  observed_at: string;
  site_key: string;
  site_name: string;
  camera_key: string;
  camera_label: string;
  events: string[];
  description: string;
  extra: Record<string, unknown> | null;
  review: Review | null;
  review_wrong_events: string[];
  review_missed_events: string[];
  review_note: string | null;
  reviewed_at: string | null;
}

export interface AnalysisRead {
  id: string;
  kind: string;
  status: string;
  error: string | null;
  model: string;
  started_at: string;
  latency_ms: number;
  input_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export interface ObservationDetail extends ObservationRead {
  analysis: AnalysisRead;
  siblings: ObservationRead[];
}

export interface ReviewWrite {
  review: Review;
  wrong_events: string[];
  missed_events: string[];
  note: string | null;
}

export interface ObservationFilters {
  only_events: boolean;
  unreviewed: boolean;
  site: string | null;
  event: string | null;
  before: string | null;
}
