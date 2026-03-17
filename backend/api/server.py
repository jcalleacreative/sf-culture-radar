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

SIGNAL_WEIGHTS = {
    "rare_event": 4,
    "internet_discourse": 3,
    "tech_ai": 2,
    "algorithm_logic": 2,
    "local_absurdity": 2,
}
REDDIT_SOURCE_BONUS = 2


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


DB_FIELDS = (
    "id", "title", "url", "source", "timestamp", "created_at",
    "upvotes", "comments", "llm_score", "popularity_score", "category", "explanation", "signals", "playable"
)


def _compute_derived_score(llm_score: float | None, signals: list[str], source: str) -> float | None:
    if llm_score is None:
        return None
    score = llm_score
    score += sum(SIGNAL_WEIGHTS.get(s, 0) for s in signals)
    if source and source.lower().startswith("r/"):
        score += REDDIT_SOURCE_BONUS
    return score


def _rows_to_dicts(rows) -> list[dict]:
    result = []
    for row in rows:
        d = {f: row[f] for f in DB_FIELDS}
        # Deserialize signals from JSON string to list
        raw_signals = d.get("signals")
        signals = json.loads(raw_signals) if raw_signals else []
        d["signals"] = signals
        d["playable"] = bool(d["playable"]) if d["playable"] is not None else None
        d["derived_score"] = _compute_derived_score(d["llm_score"], signals, d["source"])
        result.append(d)
    return result


@app.get("/stories")
def get_stories(
    category: Optional[str] = Query(default=None),
    min_llm_score: Optional[float] = Query(default=None),
):
    query = f"SELECT {', '.join(DB_FIELDS)} FROM stories WHERE 1=1"
    params: list = []

    if category is not None:
        query += " AND category = ?"
        params.append(category)
    if min_llm_score is not None:
        query += " AND llm_score >= ?"
        params.append(min_llm_score)

    query += " ORDER BY timestamp DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return _rows_to_dicts(rows)


@app.get("/week")
def get_week(
    limit: int = Query(default=10, ge=1, le=100),
    category: Optional[str] = Query(default=None),
):
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=7)).isoformat()

    # Fetch playable stories from the last 7 days, scored and ranked
    query = f"SELECT {', '.join(DB_FIELDS)} FROM stories WHERE timestamp >= ? AND playable = 1"
    params: list = [cutoff]

    if category is not None:
        query += " AND category = ?"
        params.append(category)

    query += " ORDER BY llm_score DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    stories = _rows_to_dicts(rows)

    # Sort by derived_score (accounts for signals + reddit bonus) then take top N
    stories.sort(key=lambda s: s["derived_score"] if s["derived_score"] is not None else 0, reverse=True)
    return stories[:limit]
