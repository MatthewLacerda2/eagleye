"""Generate monitoring/grafana/dashboards/eagleye.json.

    python3 monitoring/build_dashboard.py monitoring/grafana/dashboards/eagleye.json
    python3 monitoring/build_dashboard.py sql   # print the Postgres queries, to test them
"""

import json, sys

PROM = {"type": "prometheus", "uid": "prometheus"}
PG = {"type": "grafana-postgresql-datasource", "uid": "eagleye-db"}

SQL = {
 "precision": """SELECT e AS event,
  count(*) AS reviewed,
  count(*) FILTER (WHERE NOT (e = ANY(o.review_wrong_events))) AS right,
  round(100.0 * count(*) FILTER (WHERE NOT (e = ANY(o.review_wrong_events))) / count(*), 1) AS precision_pct
FROM observations o, unnest(o.events) AS e
WHERE o.review IS NOT NULL AND $__timeFilter(o.observed_at)
GROUP BY e ORDER BY e""",
 "misses": """SELECT m AS event, count(*) AS missed
FROM observations o, unnest(o.review_missed_events) AS m
WHERE $__timeFilter(o.observed_at)
GROUP BY m ORDER BY missed DESC""",
 "coverage": """SELECT
  count(*) FILTER (WHERE cardinality(events) > 0) AS flagged,
  count(*) FILTER (WHERE cardinality(events) > 0 AND review IS NOT NULL) AS flagged_reviewed,
  count(*) FILTER (WHERE review IS NOT NULL) AS reviewed_total
FROM observations WHERE $__timeFilter(observed_at)""",
 "cost_site": """SELECT date_trunc('day', a.started_at) AS time, s.name AS metric, sum(a.cost_usd)::float AS value
FROM analyses a JOIN sites s ON s.id = a.site_id
WHERE $__timeFilter(a.started_at)
GROUP BY 1, 2 ORDER BY 1""",
 "events_camera": """SELECT s.name AS site, c.label AS camera, e AS event, count(*) AS n
FROM observations o JOIN cameras c ON c.id = o.camera_id JOIN sites s ON s.id = c.site_id,
  unnest(o.events) AS e
WHERE $__timeFilter(o.observed_at)
GROUP BY 1, 2, 3 ORDER BY n DESC LIMIT 50""",
}

if sys.argv[1:] == ["sql"]:
    for name, q in SQL.items():
        print(f"-- {name}\n" + q.replace("$__timeFilter(o.observed_at)", "TRUE")
              .replace("$__timeFilter(observed_at)", "TRUE")
              .replace("$__timeFilter(a.started_at)", "TRUE") + ";")
    sys.exit()

panels, y = [], 0
def panel(title, kind, w, h, targets, ds, unit=None, desc=None, x=0, extra=None):
    p = {"id": len(panels) + 1, "title": title, "type": kind, "datasource": ds,
         "gridPos": {"x": x, "y": y, "w": w, "h": h}, "targets": targets,
         "fieldConfig": {"defaults": ({"unit": unit} if unit else {}), "overrides": []}, "options": {}}
    if desc: p["description"] = desc
    if extra: p.update(extra)
    panels.append(p)

def prom(expr, legend=""):
    return {"datasource": PROM, "expr": expr, "legendFormat": legend, "refId": chr(65 + len(legend) % 26)}

def pg(sql, fmt="table"):
    return {"datasource": PG, "rawSql": sql, "format": fmt, "rawQuery": True, "editorMode": "code", "refId": "A"}

panel("Spend, last 24 h", "stat", 4, 4, [prom("sum(increase(eagleye_cost_usd_total[24h]))")], PROM, "currencyUSD")
panel("Cache read share, last hour", "stat", 4, 4, [prom('sum(rate(eagleye_tokens_total{type="cache_read"}[1h])) / sum(rate(eagleye_tokens_total{type=~"input|cache_read|cache_write"}[1h]))')], PROM, "percentunit", "Share of input tokens served from the prompt cache. Near 0 means something breaks the cached prefix.", x=4)
panel("Cameras online", "stat", 4, 4, [prom("eagleye_cameras_online")], PROM, x=8)
panel("Budget cap active", "stat", 4, 4, [prom("max(eagleye_budget_paused)")], PROM, desc="1 while the daily budget blocks model calls.", x=12)
panel("Frames sent per hour", "stat", 4, 4, [prom("sum(increase(eagleye_frames_sent_total[1h]))")], PROM, x=16)
panel("Frames skipped per hour", "stat", 4, 4, [prom("sum(increase(eagleye_frames_skipped_total[1h]))")], PROM, desc="Unchanged frames that never reached the model (free).", x=20)
y += 4
panel("Spend per hour", "timeseries", 12, 8, [prom("sum(increase(eagleye_cost_usd_total[1h]))", "USD")], PROM, "currencyUSD")
panel("Tokens per minute by type", "timeseries", 12, 8, [prom("sum by (type) (rate(eagleye_tokens_total[5m])) * 60", "{{type}}")], PROM, x=12)
y += 8
panel("Model calls per hour", "timeseries", 12, 8, [prom("sum by (kind, status) (increase(eagleye_analyses_total[1h]))", "{{kind}} {{status}}")], PROM)
panel("Frames per minute: sent vs skipped", "timeseries", 12, 8, [prom("sum by (reason) (rate(eagleye_frames_sent_total[5m])) * 60", "sent {{reason}}"), prom("sum by (reason) (rate(eagleye_frames_skipped_total[5m])) * 60", "skipped {{reason}}")], PROM, x=12)
y += 8
panel("Captures per minute by result", "timeseries", 8, 8, [prom("sum by (result) (rate(eagleye_captures_total[5m])) * 60", "{{result}}")], PROM)
panel("Latency p95", "timeseries", 8, 8, [prom("histogram_quantile(0.95, sum by (le) (rate(eagleye_capture_seconds_bucket[15m])))", "capture"), prom("histogram_quantile(0.95, sum by (le) (rate(eagleye_analysis_seconds_bucket[15m])))", "model call")], PROM, "s", x=8)
panel("Alerts per hour", "timeseries", 8, 8, [prom("sum by (status) (increase(eagleye_alerts_total[1h]))", "{{status}}")], PROM, x=16)
y += 8
panel("Precision per event type (reviewed)", "table", 12, 8, [pg(SQL["precision"])], PG, desc="Of the reviewed observations that flagged an event, how many a person kept (not marked wrong).")
panel("Missed events (from reviews)", "table", 6, 8, [pg(SQL["misses"])], PG, x=12)
panel("Review coverage", "table", 6, 8, [pg(SQL["coverage"])], PG, x=18)
y += 8
panel("Spend per site per day", "barchart", 12, 9, [pg(SQL["cost_site"], "time_series")], PG, "currencyUSD")
panel("Events per camera", "table", 12, 9, [pg(SQL["events_camera"])], PG, x=12)

for p in panels:  # unique refIds per panel
    for i, t in enumerate(p["targets"]):
        t["refId"] = chr(65 + i)

dashboard = {"uid": "eagleye", "title": "Eagleye", "tags": ["eagleye"], "timezone": "browser",
             "schemaVersion": 41, "version": 1, "refresh": "1m",
             "time": {"from": "now-24h", "to": "now"}, "panels": panels}
json.dump(dashboard, open(sys.argv[1], "w"), indent=2)
print(len(panels), "panels")
