# Eagleye — design

2026-11-02 · status: draft for the first proof of concept (PoC)

## Intent

Eagleye replaces the night watchman: the person who stays awake in front of a
wall of 10–40 camera feeds and calls on the radio when something happens. It is
a self-hosted service — one `docker compose up` — that looks at camera feeds on
its own, asks Claude Haiku whether any event from a **catalog the operator
defines** is happening, stores every decision, and sends an alert by webhook.

There is **zero human input in operation**. Humans only *validate*: they look at
what Eagleye decided and mark it right or wrong, and those marks become the
quality metrics. Every event worth knowing about is assumed to be catalogued in
advance; a security company guarding a building swaps "unauthorized person
boarding the vessel" for "person entering the building outside the front desk"
by editing one YAML file, not code.

It is open source and generic. The first user is a fleet of river vessels with
~10 cameras each, but nothing in the code or the repository may name that user,
its clients, its camera vendor, or contain any camera URL (see *Anti-goals*).

## Goals

1. **Works from one compose file.** The operator writes `config/catalog.yaml`
   (what to look for) and `config/sites.yaml` (which cameras), sets
   `ANTHROPIC_API_KEY`, and runs `docker compose up`.
2. **Cheap enough to watch everything all the time.** A frame that did not change
   never reaches the model; frames are downscaled; the prompt is layered for
   prompt caching.
3. **Measurable.** Cost, tokens, cache hit rate, camera health and decision
   volume are visible in Grafana; precision comes from human review marks.
4. **Good watchman.** On a morning after a night run, a person can open the admin
   page, see what Eagleye flagged, and judge in a few minutes whether it did the
   job.

## Non-goals (v1)

- **Inbound event webhooks** (edge devices such as an AI camera box pushing
  "person detected" events). Phase 2, together with a small simulator service
  that runs a tiny detector on the same feeds and fires those webhooks. The PoC
  has no such device.
- **Embeddings** (e.g. a multimodal embedding model + pgvector for "find frames
  like this"). Phase 2 — nothing consumes them yet. Frames are stored as JPEGs,
  which is what review needs. pgvector already ships in the Postgres image.
- **Automatic evaluation by a stronger model** (Sonnet/Opus as judge, batch
  mode). Later; v1 review is a person.
- Billing, multi-tenancy, a camera-management API, live video playback.

## Anti-goals (failure even if it works)

- **The public repository leaks the first user's data**: company or client names,
  vessel names, camera URLs, frames. Real site/camera config lives in
  `config/local/` (git-ignored); the repo ships only a fictional example.
- **It needs a person to keep running** — restarting crashed loops, clearing
  disks, re-warming caches by hand.
- **Cost grows with idle cameras.** A static scene must cost bandwidth, not
  tokens.
- **A silent runaway bill.** A daily spend cap stops model calls when reached.

## Vocabulary

| Term | Meaning |
| --- | --- |
| **Catalog** | The operator's definition of what matters: general instructions plus a list of event types. One per deployment. |
| **Event type** | `key` (stable id, e.g. `no_ppe`), `name`, `description` (what counts), `counter_examples` ("looks like it, but is not"), `severity` (`info`/`warning`/`critical`), `alert` (bool). |
| **Site** | A group of cameras that share context: a vessel, a building. Has a free-text `context` (what it is, who is expected there, what each area is for) and a `timezone`. |
| **Camera** | Belongs to a site. `key`, `label`, `description` (what it frames), `source_url` (anything ffmpeg reads; HLS first), optional `crop` and `ignore` rectangles, `enabled`. |
| **Round** | One pass over a site's cameras: grab a frame from each, filter, maybe analyze. |
| **Analysis** | One Claude call for one site in one round, covering the cameras that changed. |
| **Observation** | One camera's result inside an analysis: detected event keys, a short description, the frame. This is what a person reviews. |

## How it works

### Processes

One backend image, two processes:

- **`api`** — FastAPI: auth, admin endpoints, frame files, `/health`.
- **`worker`** — an asyncio loop: rounds → capture → change filter → analysis →
  alerts, plus keep-alive and retention. Exposes Prometheus metrics on its own
  port.

Plus Postgres (with pgvector, unused in v1), the React admin frontend, and an
optional `monitoring` compose profile with Prometheus and Grafana (provisioned
datasources + a shipped dashboard).

### Configuration

- `config/catalog.yaml` and `config/sites.yaml` are the **source of truth**. The
  worker syncs them into the database at startup (upsert by key; a camera removed
  from YAML is disabled, never deleted, so history keeps its foreign keys).
- The repo ships `config/catalog.example.yaml` and `config/sites.example.yaml`
  (fictional). The compose file mounts `config/` read-only; the path to each
  file is an env var so a deployment can point at `config/local/...`.
- Everything numeric is an env var with a default (intervals, thresholds, caps,
  prices), centralized in `pydantic-settings`.

### The round (per site)

1. **Schedule.** Each site runs a round every `ROUND_INTERVAL_SECONDS`
   (default 120). Sites start staggered so their first calls do not all write
   the shared catalog cache at once (parallel calls with the same prefix each
   pay the write).
2. **Capture.** For each enabled camera, grab one frame with ffmpeg (bounded
   concurrency, timeout). HLS sources start at the newest segment
   (`-live_start_index -1`), so a grab downloads one segment; other sources use
   ffmpeg's defaults. A failure marks the camera `offline` (normal — remote
   uplinks drop for hours), records it, and moves on.
3. **Prepare.** Apply the camera's `crop`, then downscale so the long side is at
   most `FRAME_MAX_SIDE` (default 640) and encode JPEG (~20 KB). Image tokens
   scale with pixel area (~one token per 28×28 patch, verify with
   `count_tokens`): 640×437 ≈ 370 tokens.
4. **Change filter (no AI).** Compare the frame with the **last frame of that
   camera that was sent to the model** (not the previous capture, so slow drift
   accumulates). Grayscale thumbnail split into a grid (e.g. 16×12 cells); a
   cell "changed" when its mean absolute difference exceeds
   `CHANGE_CELL_THRESHOLD`; the frame changed when at least
   `CHANGE_MIN_CELLS` cells changed. On-screen overlays (DVR clocks, logos,
   channel labels) sit in a different place on every camera, so hand-drawn
   masks do not scale to hundreds of cameras. Instead each camera keeps an
   **auto-mask**: cells that changed in more than ~80% of its last N captures
   (clocks, flicker) are ignored. Optional `ignore` rectangles still exist for
   the rare case the auto-mask misses. Below the bar → skipped, counted in
   metrics. A camera with no previous sent frame always
   passes. Also passes if its last sent frame is older than
   `MAX_UNSENT_MINUTES` (default 60), so a camera is never blind forever because
   of a bad threshold.
5. **Analyze** the cameras that passed, in **one call per site** (see *The
   Claude call*). If none passed, no call.
6. **Store** the analysis and one observation per camera, write the frames to
   the frames volume, update each camera's "last sent frame".
7. **Alert** (see *Alerts*).

### The Claude call

Model `claude-haiku-5-5` (env `ANTHROPIC_MODEL`), official `anthropic` Python
SDK, non-streaming. Adaptive thinking (the model default; omit `thinking`),
`output_config.effort` **`medium`** set explicitly. No `temperature`/`top_p`/
`top_k` (rejected on this model). Prompt layers, in render order:

| Layer | Content | Changes when | Cache |
| --- | --- | --- | --- |
| 1. Catalog | `system`: role, catalog instructions, every event type with description and counter-examples, output rules | the catalog file changes | breakpoint, `ttl: "1h"` |
| 2. Site | second `system` block (images in `messages` would invalidate a messages-cache breakpoint): site context, timezone, the list of **all** the site's cameras with key, label and description, in a fixed order | the site's YAML changes | breakpoint, `ttl: "1h"` |
| 3. Round | current UTC and local time; for each camera that passed the filter, a text line naming it, then its image | every call | none |

Determinism rules: no time, IDs or random order in layers 1–2; lists sorted by
key; YAML rendered through one function used by both real calls and keep-alive.
A layer-1 under 512 tokens silently does not cache — fine, the cost of that is
negligible, but the metric will show it.

**Output — semi-fixed schema via structured outputs** (`output_config.format`,
JSON schema built at startup from the catalog):

```json
{
  "cameras": [
    {
      "camera": "<camera key — enum of the site's keys>",
      "events": ["<event key — enum of catalog keys>"],
      "description": "<= 100 chars, what is happening>",
      "extra": {}
    }
  ]
}
```

`events` empty means nothing to report. `description` is capped at 100
characters by the prompt and truncated on store. `extra` is an optional,
operator-defined JSON schema (`catalog.yaml` → `extra_schema`) for fields a user
needs that Eagleye does not interpret; it is stored and forwarded in alerts
verbatim. The core fields are fixed because Eagleye itself reads them (alerts,
metrics, review).

Guards: at most `MAX_CAMERAS_PER_CALL` images (default 20, more → split into
calls); estimated prompt kept well under 100K tokens — on Haiku 5.5 a prompt
over 100K tokens is billed at 5× input and output (verified against the API
reference, 2026-11-02). `max_tokens` large enough for thinking + JSON
(default 8000; thinking counts against it). Retries: SDK defaults for 429/5xx; a malformed or refused
response is stored as a failed analysis and counted, not retried in a loop.

Every analysis records `usage.input_tokens`, `cache_read_input_tokens`,
`cache_creation_input_tokens`, `output_tokens`, latency, model, stop reason,
and a computed `cost_usd` from a price table in settings (defaults: Haiku 5.5
$0.10 / $0.50 per MTok, cache read 0.1×, 1 h write 2×; verified 2026-11-02).

### Keep-alive

Per site: if no analysis started in the last `KEEPALIVE_AFTER_MINUTES`
(default 55, must stay under the 60-minute TTL), send a keep-alive built by the
same function as a real call, with a placeholder round layer (text only, no
images). `max_tokens: 0` cannot be combined with `output_config.format`, so the
keep-alive uses `max_tokens: 1` with the identical request otherwise. It is
recorded as an analysis of kind `keepalive`. **Verify in the first PoC hour**
that the next real call shows `cache_read_input_tokens` > 0; if the API rejects
the shape or it never hits, set `KEEPALIVE_ENABLED=false` — a cold layer costs
~$0.001 per site on Haiku, so the fallback is cheap. Keep-alive is skipped
while every camera of a site is offline.

### Daily spend cap

`DAILY_BUDGET_USD` (default 25). When today's (UTC) summed `cost_usd` reaches
it, the worker stops model calls (capture and filter continue), logs it, sets a
metric, and resumes at the next UTC day.

### Alerts

When an observation contains an event type with `alert: true`, POST a JSON
payload to every URL in `ALERT_WEBHOOK_URLS`: site, camera, event keys with
name and severity, description, `extra`, timestamp, a URL to the observation in
the admin, and an HMAC-SHA256 signature header when `ALERT_WEBHOOK_SECRET` is
set. Cooldown: the same camera + event key alerts at most once per
`ALERT_COOLDOWN_MINUTES` (default 10). Deliveries are stored with status;
failures retry with backoff a few times, then stay failed and counted.

### Storage

Postgres tables (names indicative): `sites`, `cameras`, `analyses`,
`observations` (with `events text[]`, `description`, `frame_path`, and the
review: `review` = null/`correct`/`incorrect`, `review_wrong_events text[]`,
`review_missed_events text[]`, `review_note`, `reviewed_at`),
`alert_deliveries`, plus the template's `users`. Frames: JPEG files on a
volume, path `frames/<site>/<camera>/<date>/<uuid>.jpg`. Retention:
`RETENTION_DAYS` (default 14) deletes old frames and observations daily
(reviewed observations kept). Schema changes go through Alembic (the template's
`create_all` is not enough once the schema evolves during the PoC).

### Admin page

The template's React app (login, shadcn, i18n). Three pages:

1. **Observations** — newest first, thumbnail + site/camera + events +
   description + time. Filters: only events / site / event type / unreviewed.
   Each row: **Correct** / **Incorrect** buttons (+ optional note). This is the
   morning review. *Incorrect* opens two optional multi-selects: which flagged
   events were wrong, and which catalog events were missed. Observations with
   no events are reviewable too (the "only events" filter off), which is how
   misses get measured.
2. **Observation detail** — full frame, all fields, the analysis's cost and
   tokens, the other cameras in the same analysis.
3. **Cameras** — per site, each camera's state (online/offline, last capture,
   last sent frame thumbnail), so a person can see the watch is actually
   watching.

Metrics stay in Grafana, not in the admin.

### Metrics

Prometheus (from the worker): captures by result (ok/offline/error), capture
latency, frames skipped by the change filter, analyses by kind/result, tokens
by type (input / cache read / cache write / output), cost USD, analysis
latency, observations by event key, alerts by result, budget-cap state, cameras
online.

Grafana gets two datasources: Prometheus (operations) and Postgres (quality).
Per event type, over reviewed observations: precision = flagged and not in
`review_wrong_events` / flagged; misses = count in `review_missed_events`.
Also review coverage, cost per site per day, events per camera per day. One
dashboard JSON ships in the repo.

## The first PoC

- A week-long run on a few hundred cameras. The deployment's real config lives
  in the git-ignored `config/local/`, written by a one-off local script that is
  not part of the product. Camera `description`s start empty (the model sees the
  image; descriptions are added as the PoC teaches what helps). The auto-mask
  handles overlays; no hand-drawn `ignore` rectangles to start.
- Alerts: no webhook receiver during the PoC (`ALERT_WEBHOOK_URLS` empty);
  alert-worthy observations are visible in the admin, which is never exposed
  publicly.
- Catalog: `smoking`, `phone_use`, `sleeping`, `other_vessel` (another vessel,
  barge, speedboat or jet ski approaching or alongside, not part of the own
  convoy). Phone use and sleeping count only **on duty** — at the helm,
  operating machinery, on watch; a phone at the mess table is not an event.
- Success: after a night, the observations page shows flagged events a person
  agrees with, few incorrect ones, and Grafana shows cost and cache behaving as
  predicted.

## Phase 2 (recorded, not built)

Inbound event webhooks + a detector simulator; embeddings; camera-management
API; stronger-model evaluation over a sample; hosted-service
questions.

## Decided

- Stack: the GoldStandard template — FastAPI 4-layer backend, React + shadcn +
  Tailwind v4 + bun frontend, Postgres with pgvector, Makefile gates, CI.
- Ronda-only PoC; one Claude call per site per round; structured outputs; effort
  medium; description ≤ 100 chars; human only validates.
- YAML config as source of truth; real config git-ignored.
- License: Apache-2.0.
- Public repository on the owner's personal GitHub account.

## Left to the builder

Exact change-filter math and defaults (to be tuned on real feeds), table
columns, admin layout, metric names, retry/backoff details, how sites are
scheduled inside the worker.
