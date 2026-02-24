# ygg-torznab

Self-hosted [Torznab](https://torznab.github.io/spec-1.3-draft/revisions/1.0-Torznab-Torrent-Support.html) proxy for [YGGtorrent](https://www.yggtorrent.org), with automatic Cloudflare bypass.

Allows Prowlarr, Sonarr, Radarr and other *arr apps to search and download from YGG through a standard Torznab API.

## Features

- Standard Torznab API (`search`, `tvsearch`, `movie`, `download`, `caps`)
- Automatic Cloudflare challenge bypass via [cf-clearance-scraper](https://github.com/zfcsoftware/cf-clearance-scraper)
- Proactive cookie refresh (no request failures due to expired cookies)
- Support for both turbo and non-turbo YGG accounts
- Optional API key authentication
- Docker healthcheck with login verification

## Quick Start

### One-liner

```bash
mkdir ygg-torznab && cd ygg-torznab && curl -fsSL https://raw.githubusercontent.com/Kenshin9977/ygg-torznab/master/docker-compose.yml -o docker-compose.yml && curl -fsSL https://raw.githubusercontent.com/Kenshin9977/ygg-torznab/master/.env.example -o .env && nano .env && docker compose up -d
```

This downloads the compose file and `.env` template, opens the editor to fill in your credentials, then starts the stack.

### Step by step

#### 1. Create `.env`

```bash
cp .env.example .env
```

Edit `.env` with your YGG credentials:

```env
YGG_USERNAME=your_username
YGG_PASSWORD=your_password
API_KEY=your_secret_key
```

#### 2. Start

```bash
docker compose up -d
```

The proxy starts on port **8715**. The `cf-clearance` sidecar handles Cloudflare challenges automatically.

#### 3. Add to Prowlarr

In Prowlarr, add a **Generic Torznab** indexer:

| Field | Value |
|-------|-------|
| URL | `http://<host>:8715` |
| API Key | The `API_KEY` from your `.env` |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `YGG_USERNAME` | *(required)* | YGG account username |
| `YGG_PASSWORD` | *(required)* | YGG account password |
| `YGG_DOMAIN` | `www.yggtorrent.org` | YGG domain |
| `TURBO_USER` | `false` | Set to `true` if you have a turbo account (skips 30s download wait) |
| `API_KEY` | *(empty)* | API key for Torznab endpoint authentication |
| `CF_REFRESH_INTERVAL` | `1500` | Seconds between proactive Cloudflare cookie refreshes |
| `LOG_LEVEL` | `info` | Logging level (`debug`, `info`, `warning`, `error`) |

## Category Mapping

| Torznab ID | Name | YGG Categories |
|------------|------|----------------|
| 1000 | Console | Jeu video, Emulation |
| 2000 | Movies | Film |
| 2060 | Movies/Concert | Concert, Spectacle, Video-clips |
| 3000 | Audio | Musique, Karaoke, Samples, Podcast Radio |
| 4000 | PC | Application |
| 5000 | TV | Serie TV, Emission TV |
| 5060 | TV/Sport | Sport |
| 5070 | TV/Anime | Animation, Animation Serie |
| 5080 | TV/Documentary | Documentaire |
| 7000 | Books | eBook |

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api?t=caps` | Torznab capabilities |
| `GET /api?t=search&q=...` | Search torrents |
| `GET /api?t=tvsearch&q=...` | TV search |
| `GET /api?t=movie&q=...` | Movie search |
| `GET /api?t=download&id=...` | Download torrent file |
| `GET /health` | Health check |

## Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest -v

# Type checking
mypy src/

# Linting
ruff check src/ tests/
```

## Architecture

```
Prowlarr/Sonarr/Radarr
        |
        v
  ygg-torznab (FastAPI, port 8715)
   |              |
   v              v
  YGG         cf-clearance-scraper
(search/dl)   (Cloudflare bypass)
```

The proxy maintains a persistent session with YGG. Cloudflare cookies are refreshed proactively every 25 minutes (configurable) in the background, so no user-facing request ever fails due to expired cookies. During a refresh, concurrent requests are held until fresh cookies are available.
