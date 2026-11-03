# Eagleye

**A self-hosted night watchman for your cameras.** Eagleye looks at your camera
feeds on its own, asks Claude Haiku whether any event from a catalog *you*
define is happening, stores every decision, and sends an alert by webhook. Nobody
has to stare at a wall of screens: people only review what it decided.

- **You define what matters** in one YAML file — "someone smoking on deck",
  "a boat approaching", "a person entering the building outside the front
  desk". Swap the catalog, and the same service guards a fleet, a building or a
  warehouse.
- **Cheap enough to watch everything all the time.** A frame that did not change
  never reaches the model; frames are downscaled; the prompt is layered for
  prompt caching; a daily budget cap stops spending.
- **Measurable.** An admin page to mark each decision right or wrong, and a
  Grafana dashboard with cost, cache behaviour, camera health and precision per
  event type.

The design lives in
[`docs/superpowers/specs/2026-11-02-eagleye-design.md`](docs/superpowers/specs/2026-11-02-eagleye-design.md).

## How it works

```
cameras ──ffmpeg──▶ frame ──▶ change filter ──changed──▶ Claude Haiku ──▶ observations ──▶ admin review
                                   │ unchanged                │                  └──▶ webhook alerts
                                   ▼                          ▼
                              skipped (free)          usage + cost ──▶ Prometheus / Grafana
```

Every round (default 2 minutes) the worker grabs one frame per camera, keeps
only the cameras whose picture changed, and sends them — grouped per site — to
Claude Haiku 5.5 with a fixed JSON output: which catalog events each camera
shows and a short description.

## Quick start

Requirements: Docker with Compose, an Anthropic API key.

```bash
cp .env.example .env                       # set ANTHROPIC_API_KEY, JWT_SECRET, admin password
mkdir -p config/local
cp config/catalog.example.yaml config/local/catalog.yaml
cp config/sites.example.yaml   config/local/sites.yaml
# edit both files, then point CATALOG_PATH / SITES_PATH in .env at config/local/...
docker compose up -d                        # postgres, api, worker, admin
docker compose --profile monitoring up -d   # + Prometheus and Grafana
```

- Admin: <http://localhost:3000>
- Grafana: <http://localhost:3001>

`config/local/` and `data/` are git-ignored: real camera addresses and captured
frames never enter the repository.

## Development

Built on the GoldStandard template: a strict 4-layer FastAPI backend, an
SDK-layered React frontend, and one `Makefile` that defines every quality gate.
The working contract for humans and agents is [`CLAUDE.md`](CLAUDE.md).

```bash
docker compose up -d --wait postgres
make back-install front-install
make check PYTHON=.venv/bin/python   # PYTHON is relative to backend/
```

## License

[Apache-2.0](LICENSE).
