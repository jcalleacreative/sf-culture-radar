# SF Sketch Radar — Backend

A lightweight Python backend for SF Sketch Radar, designed to run on a Raspberry Pi.
Collects signal from multiple sources over a rolling 7-day window, scores items for
comedy relevance using an LLM, and serves a filterable feed via a FastAPI REST API.

---

## Project Structure

```
backend/
  collectors/         # One collector per source (Reddit, RSS, YouTube, etc.)
  llm/                # LLM headline analyzer
  db/                 # SQLite database setup
  api/                # FastAPI server
  jobs/               # Cron-runnable scripts
  config/             # Settings loaded from .env
  requirements.txt
  .env.example
```

---

## Install

```bash
cd backend
pip install -r requirements.txt
```

---

## Configure

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Key variables:

| Variable | Description |
|---|---|
| `DATABASE_PATH` | Path to SQLite database file |
| `REDDIT_CLIENT_ID` | Reddit API client ID |
| `REDDIT_CLIENT_SECRET` | Reddit API client secret |
| `REDDIT_USER_AGENT` | Reddit API user agent string |
| `REDDIT_POST_LIMIT` | Posts per subreddit per run (default: `25`) |
| `YOUTUBE_API_KEY` | Google Cloud API key with YouTube Data API v3 enabled (optional) |
| `LLM_PROVIDER` | `openai` or `anthropic` |
| `OPENAI_API_KEY` | OpenAI key (if using OpenAI) |
| `ANTHROPIC_API_KEY` | Anthropic key (if using Anthropic) |
| `LLM_MODEL_OPENAI` | OpenAI model (default: `gpt-4o-mini`) |
| `LLM_MODEL_ANTHROPIC` | Anthropic model (default: `claude-haiku-4-5-20251001`) |
| `API_KEY` | Optional API key for the server (see below) |

---

## Sources

The system pulls from five source types. Each represents a different kind of attention.

### 1. Reddit (PRIMARY)
- Subreddits: `r/sanfrancisco`, `r/AskSF`, `r/bayarea`, `r/technology`
- Uses the PRAW library with Reddit API credentials
- Hot posts fetched per run; duplicates silently ignored
- Popularity score: `log(upvotes + 1) + log(comments + 1)`

### 2. Local SF News (RSS)
- Feeds: Mission Local, SF Standard, SFGATE
- No API key required — standard RSS/Atom parsing via feedparser
- Popularity score: `1.0` (no engagement metrics available)

### 3. Google Trends
- US-wide trending search queries via the unofficial `pytrends` library
- **No API key required**
- Limitations:
  - `pytrends` is an unofficial wrapper and may break if Google changes their internal API
  - Google rate-limits aggressively; running more than once per day risks 429 errors
  - Results are US-wide, not SF-specific
  - Run frequency recommendation: once per day at most

### 4. YouTube
- Trending videos in the US via the YouTube Data API v3
- **Requires `YOUTUBE_API_KEY`** (Google Cloud project with YouTube Data API v3 enabled)
- Without the key, this collector is skipped gracefully (no error)
- Limitations:
  - Free quota: 10,000 units/day; one call to `videos.list` costs ~1 unit
  - Results are US-wide, not SF-specific
  - Popularity score: `log(viewCount + 1)`, capped at 10
  - How to get a key: https://console.cloud.google.com → Enable YouTube Data API v3 → Create credentials → API key

### 5. BlueSky
- Popular posts from the public "What's Hot" feed via the AT Protocol public API
- **No API key required**
- Limitations:
  - "What's Hot" is curated and updates slowly — once or twice per day is appropriate
  - Post text is used as the title (truncated to 120 characters); no separate headline
  - Likes stored as `upvotes`, reposts stored as `comments`
  - Results are global, not SF-specific

---

## Run Collectors Manually

From the `backend/` directory:

```bash
python jobs/run_collectors.py
```

Runs all five collectors in sequence. Each collector catches its own errors and
continues — a single source failure won't stop the others.

---

## Run Analysis Manually

```bash
python jobs/run_analysis.py
```

Picks up to 30 unscored stories and sends each headline to the configured LLM.
Each story gets an `llm_score` (0–10), `playable` flag, `category`, `signals`,
and one-sentence `explanation`.

---

## Start the API Server

```bash
cd backend
uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload
```

---

## API Reference

### `GET /week`

The primary feed endpoint. Returns items from a rolling 7-day window.

**Default behavior:**
- Window: last 7 days (now − 7 days → now)
- Limit: 50 items
- Sort: newest first
- Includes all items regardless of `playable` flag

**Query parameters:**

| Param | Type | Description |
|---|---|---|
| `limit` | int | Max items to return (default `50`, max `500`) |
| `source` | string | Filter by source group: `reddit`, `rss`, `google_trends`, `youtube`, `bluesky` — or any exact source name stored in the DB |
| `category` | string | Filter by LLM-assigned category label |
| `min_llm_score` | float | Minimum `llm_score` (0–10) |
| `playable` | bool | `true` = only playable items; `false` = only non-playable; omit = all |
| `sort_by` | string | `newest` (default) \| `llm` \| `popularity` |
| `from` | string | Start of date window (ISO 8601, e.g. `2026-03-10`) |
| `to` | string | End of date window (ISO 8601, e.g. `2026-03-17`) |

**Examples:**

```
GET /week
GET /week?source=reddit
GET /week?sort_by=llm
GET /week?sort_by=popularity
GET /week?playable=true
GET /week?min_llm_score=7
GET /week?source=reddit&sort_by=llm&limit=20
GET /week?from=2026-03-10&to=2026-03-17
```

**Response shape** (per item):

```json
{
  "id": 42,
  "title": "Waymo cars blocking traffic after SF concert",
  "url": "https://www.reddit.com/r/sanfrancisco/...",
  "source": "sanfrancisco",
  "timestamp": "2026-03-15T18:00:00+00:00",
  "created_at": "2026-03-15T18:05:00+00:00",
  "upvotes": 1200,
  "comments": 340,
  "llm_score": 8.0,
  "popularity_score": 10.2,
  "playable": true,
  "signals": ["local_absurdity", "internet_discourse"],
  "category": "tech culture",
  "explanation": "Autonomous cars creating a traffic comedy sketch writes itself."
}
```

Fields `upvotes` and `comments` are `null` for sources that don't provide engagement
metrics (RSS, Google Trends, YouTube).

### `GET /stories`

All stories in the database, newest first. Useful for debugging.

Optional filters: `category`, `min_llm_score`, `source`

---

## Scoring

### popularity_score
Computed at collection time:
- **Reddit:** `log(upvotes + 1) + log(comments + 1)` — roughly 0–10 for typical posts
- **YouTube:** `log(viewCount + 1)`, hard-capped at `10.0`. A video with 100M views
  scores the same as one with 1M — YouTube scores will always be ≤ 10. Reddit viral
  posts are not capped and can exceed 10.
- **BlueSky:** `log(likes + 1) + log(reposts + 1)`, same formula as Reddit.
- **RSS / Google Trends:** `1.0` (no engagement data available).

### llm_score
Integer 0–10 assigned by the LLM after analysis. Reflects estimated comedy sketch
potential for a 25–40 SF audience. Null until `run_analysis.py` is run.

### playable
Boolean set by the LLM. `true` means the item has sketch potential.
Bureaucratic/policy-only stories receive `playable=false` and `llm_score ≤ 3`.

### signals
Array of tags applied by the LLM:
- `rare_event` — unusual real-world event
- `internet_discourse` — likely to go viral or spark debate
- `tech_ai` — AI or tech company culture
- `algorithm_logic` — data-driven thinking applied to human behavior
- `local_absurdity` — strange behaviors specific to SF or the Bay Area

The frontend can use these signals to weight or filter results. The API does not
apply signal-based weighting; that is left to the consumer.

---

## Cron Setup (Raspberry Pi)

Edit your crontab with `crontab -e`:

```cron
# Collect new stories every hour
0 * * * * cd /home/pi/sf-culture-radar/backend && /usr/bin/python3 jobs/run_collectors.py >> /home/pi/logs/collectors.log 2>&1

# Analyze new stories every 2 hours
30 */2 * * * cd /home/pi/sf-culture-radar/backend && /usr/bin/python3 jobs/run_analysis.py >> /home/pi/logs/analysis.log 2>&1
```

Note: If you are using Google Trends, consider reducing the collection frequency
to once or twice per day to avoid rate-limiting from Google.

---

## API Key

By default the server runs in open mode (no authentication required). To enable API
key protection before exposing the server externally, set `API_KEY` in your `.env`
file. Clients must then include the header `X-API-Key: <your_key>` with every request.
