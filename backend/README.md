# SF Sketch Radar — Backend

A lightweight Python backend for SF Sketch Radar, designed to run on a Raspberry Pi.
It collects San Francisco news from Reddit and RSS feeds, scores them for comedy sketch
potential using an LLM, and serves the results via a FastAPI REST API.

---

## Project Structure

```
backend/
  collectors/         # Reddit and RSS data collectors
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
| `LLM_PROVIDER` | `openai` or `anthropic` |
| `OPENAI_API_KEY` | OpenAI key (if using OpenAI) |
| `ANTHROPIC_API_KEY` | Anthropic key (if using Anthropic) |
| `LLM_MODEL_OPENAI` | OpenAI model (default: `gpt-4o-mini`) |
| `LLM_MODEL_ANTHROPIC` | Anthropic model (default: `claude-haiku-4-5-20251001`) |
| `REDDIT_POST_LIMIT` | Posts per subreddit per run (default: `25`) |
| `API_KEY` | Optional API key for the server (see below) |

---

## Run Collectors Manually

From the `backend/` directory:

```bash
python jobs/run_collectors.py
```

This fetches fresh stories from Reddit (`r/sanfrancisco`, `r/AskSF`, `r/bayarea`)
and RSS feeds (Mission Local, SF Standard, SFGATE, Eater SF), storing new ones in
the database. Duplicate URLs are silently ignored.

---

## Run Analysis Manually

```bash
python jobs/run_analysis.py
```

This picks up to 30 unscored stories and sends each headline to the configured LLM.
Each story gets an `llm_score` (0–10), a `category`, and a one-sentence `explanation`.

---

## Start the API Server

```bash
cd backend
uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload
```

### Endpoints

**`GET /stories`**
Returns all stories, newest first. Optional filters:
- `?category=dog+culture`
- `?min_llm_score=7`

**`GET /week`**
Returns stories from the last 7 days, sorted by `llm_score DESC`.
Optional filters: `limit`, `category`, `min_llm_score`.

---

## Cron Setup (Raspberry Pi)

Edit your crontab with `crontab -e` and add:

```cron
# Collect new stories every hour
0 * * * * cd /home/pi/sf-culture-radar/backend && /usr/bin/python3 jobs/run_collectors.py >> /home/pi/logs/collectors.log 2>&1

# Analyze new stories every 2 hours
30 */2 * * * cd /home/pi/sf-culture-radar/backend && /usr/bin/python3 jobs/run_analysis.py >> /home/pi/logs/analysis.log 2>&1
```

Make sure your `.env` file is present in `backend/` before running.

---

## Notes

### Popularity Score

The `popularity_score` field is computed at collection time:
- **Reddit:** `log(upvotes + 1) + log(comments + 1)` — roughly 0–10 for typical posts,
  but may exceed 10 for very viral content. The frontend should handle this gracefully
  (e.g. cap display at 10 or normalize).
- **RSS:** always set to `1.0`.

### LLM Score

The `llm_score` is an integer 0–10 assigned by the LLM, where 10 means maximum
comedy sketch potential. Stories are scored lazily — run `run_analysis.py` to process
the queue.

### API Key

By default the server runs in open mode (no authentication required). To enable API
key protection before exposing the server externally, set `API_KEY` in your `.env`
file. Clients must then include the header `X-API-Key: <your_key>` with every request.
