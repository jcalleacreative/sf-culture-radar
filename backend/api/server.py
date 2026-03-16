# backend/api/server.py

import logging
import sys
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Query
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


STORY_FIELDS = (
    "id", "title", "url", "source", "timestamp", "created_at",
    "upvotes", "comments", "llm_score", "popularity_score", "category", "explanation"
)


def _rows_to_dicts(rows) -> list[dict]:
    return [dict(zip(STORY_FIELDS, (row[f] for f in STORY_FIELDS))) for row in rows]


@app.get("/stories")
def get_stories(
    category: Optional[str] = Query(default=None),
    min_llm_score: Optional[float] = Query(default=None),
):
    query = f"SELECT {', '.join(STORY_FIELDS)} FROM stories WHERE 1=1"
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
    limit: int = Query(default=20, ge=1, le=200),
    category: Optional[str] = Query(default=None),
    min_llm_score: Optional[float] = Query(default=None),
):
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=7)).isoformat()

    query = f"SELECT {', '.join(STORY_FIELDS)} FROM stories WHERE timestamp >= ?"
    params: list = [cutoff]

    if category is not None:
        query += " AND category = ?"
        params.append(category)
    if min_llm_score is not None:
        query += " AND llm_score >= ?"
        params.append(min_llm_score)

    query += " ORDER BY llm_score DESC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return _rows_to_dicts(rows)
