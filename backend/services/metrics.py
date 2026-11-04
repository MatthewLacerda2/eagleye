"""Prometheus metrics exposed by the worker (scraped on METRICS_PORT)."""

from prometheus_client import Counter, Gauge, Histogram

captures_total = Counter("eagleye_captures_total", "Frame grabs by result", ["result"])
capture_seconds = Histogram(
    "eagleye_capture_seconds", "Time to grab one frame", buckets=(0.5, 1, 2, 4, 8, 15, 30)
)
frames_skipped_total = Counter(
    "eagleye_frames_skipped_total", "Frames not sent to the model", ["reason"]
)
frames_sent_total = Counter("eagleye_frames_sent_total", "Frames sent to the model", ["reason"])
analyses_total = Counter("eagleye_analyses_total", "Model calls", ["kind", "status"])
tokens_total = Counter("eagleye_tokens_total", "Tokens by type", ["type"])
cost_usd_total = Counter("eagleye_cost_usd_total", "Model spend in USD")
analysis_seconds = Histogram(
    "eagleye_analysis_seconds", "Model call latency", buckets=(1, 2, 4, 8, 15, 30, 60)
)
observations_events_total = Counter(
    "eagleye_observations_events_total", "Events reported", ["event"]
)
alerts_total = Counter("eagleye_alerts_total", "Alert deliveries", ["status"])
budget_paused = Gauge("eagleye_budget_paused", "1 while the daily budget cap blocks calls")
cameras_online = Gauge("eagleye_cameras_online", "Enabled cameras whose last grab worked")
