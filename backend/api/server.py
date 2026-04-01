# backend/api/server.py

import json
import logging
import sys
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Allow running from the backend/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import API_KEY
from db.database import get_connection, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="SF Sketch Radar API")

# CORS — allow all origins for local development.
# In production, restrict this to the actual frontend origin, e.g. ["http://localhost:3000"].
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Maps the ?source= param to the actual source values stored in the DB.
# Allows ?source=reddit to match all Reddit subreddits, etc.
SOURCE_GROUPS = {
    "reddit": ["sanfrancisco", "AskSF", "bayarea", "technology"],
    "rss": ["Mission Local", "SF Standard", "SFGATE"],
    "google_trends": ["google_trends"],
    "youtube": ["youtube"],
    "bluesky": ["bluesky"],
    "hackernews": ["hackernews"],
    "wikipedia": ["wikipedia"],
}

DB_FIELDS = (
    "id", "title", "url", "source", "timestamp", "created_at",
    "upvotes", "comments", "llm_score", "popularity_score",
    "category", "explanation", "signals", "playable",
)


@app.on_event("startup")
def on_startup():
    init_db()
    if not API_KEY:
        logger.warning("API key not configured — server running in open mode.")


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    if API_KEY:
        key = request.headers.get("X-API-Key", "")
        if key != API_KEY:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


def _rows_to_dicts(rows) -> list[dict]:
    result = []
    for row in rows:
        d = {f: row[f] for f in DB_FIELDS}
        raw_signals = d.get("signals")
        d["signals"] = json.loads(raw_signals) if raw_signals else []
        d["playable"] = bool(d["playable"]) if d["playable"] is not None else None
        result.append(d)
    return result


def _build_source_filter(source: Optional[str]) -> tuple[str, list]:
    """Return (sql_fragment, params) for a source filter, or ('', []) if no filter."""
    if source is None:
        return "", []
    group = SOURCE_GROUPS.get(source.lower())
    if group:
        placeholders = ", ".join("?" * len(group))
        return f" AND source IN ({placeholders})", list(group)
    # Exact match fallback
    return " AND source = ?", [source]


@app.post("/panel-show")
async def post_panel_show(request: Request):
    """
    Generate candidate comedy panel-show segments from a batch of local news stories.

    Input body: JSON array of story objects, each with:
      id, headline, summary, source, url, published_at, image_url (optional)

    Returns segments grouped by type (scenes, if_this_is_the_answer, truth_or_lie,
    picture_of_week, unlikely_things, wildcard) so producers can pick the final lineup,
    plus unused_stories with reasons for exclusion.
    """
    from llm.panel_show import generate_panel_show

    body = await request.json()
    if not isinstance(body, list):
        return JSONResponse(status_code=422, content={"detail": "Body must be a JSON array of stories."})

    story_count = len(body)
    logger.info("panel_show: received %d stories", story_count)

    try:
        result = generate_panel_show(body)
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        logger.error("panel_show: parse/validation failure — %s", exc)
        return JSONResponse(status_code=502, content={"detail": f"LLM response parse failure: {exc}"})

    selected = sum(len(v) for v in result["segments"].values())
    logger.info("panel_show: %d/%d stories selected as candidates", selected, story_count)

    return result


@app.get("/stories")
def get_stories(
    category: Optional[str] = Query(default=None),
    min_llm_score: Optional[float] = Query(default=None),
    source: Optional[str] = Query(default=None),
):
    query = f"SELECT {', '.join(DB_FIELDS)} FROM stories WHERE 1=1"
    params: list = []

    if category is not None:
        query += " AND category = ?"
        params.append(category)
    if min_llm_score is not None:
        query += " AND llm_score >= ?"
        params.append(min_llm_score)

    src_sql, src_params = _build_source_filter(source)
    query += src_sql
    params.extend(src_params)

    query += " ORDER BY timestamp DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return _rows_to_dicts(rows)


@app.get("/week")
def get_week(
    limit: int = Query(default=50, ge=1, le=500),
    source: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    min_llm_score: Optional[float] = Query(default=None),
    playable: Optional[bool] = Query(default=None),
    sort_by: Optional[str] = Query(default="newest"),
    from_: Optional[str] = Query(default=None, alias="from"),
    to: Optional[str] = Query(default=None),
):
    """
    Rolling 7-day feed. Returns all items from the last 7 days by default.

    Query params:
      limit         Max items to return (default 50, max 500)
      source        Filter by source group: reddit, rss, google_trends, youtube, bluesky
                    or any exact source name stored in the DB
      category      Filter by LLM-assigned category label
      min_llm_score Minimum llm_score (0–10)
      playable      true = only playable items; false = only non-playable; omit = all
      sort_by       newest (default) | llm | popularity
      from          Start of date window (ISO 8601, e.g. 2026-03-10)
      to            End of date window (ISO 8601, e.g. 2026-03-17)
    """
    now = datetime.now(tz=timezone.utc)

    if from_ is not None:
        cutoff = from_
    else:
        cutoff = (now - timedelta(days=7)).isoformat()

    if to is not None:
        ceiling = to
    else:
        ceiling = now.isoformat()

    query = f"SELECT {', '.join(DB_FIELDS)} FROM stories WHERE timestamp >= ? AND timestamp <= ?"
    params: list = [cutoff, ceiling]

    if category is not None:
        query += " AND category = ?"
        params.append(category)

    if min_llm_score is not None:
        query += " AND llm_score >= ?"
        params.append(min_llm_score)

    if playable is not None:
        query += " AND playable = ?"
        params.append(1 if playable else 0)

    src_sql, src_params = _build_source_filter(source)
    query += src_sql
    params.extend(src_params)

    sort_map = {
        "newest": "timestamp DESC",
        "llm": "llm_score DESC",
        "popularity": "popularity_score DESC",
    }
    order_clause = sort_map.get(sort_by, "timestamp DESC")
    query += f" ORDER BY {order_clause}"
    query += " LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return _rows_to_dicts(rows)
