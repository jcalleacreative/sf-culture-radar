# backend/collectors/youtube_collector.py
#
# Pulls trending videos from the YouTube Data API v3.
# Requires a Google Cloud API key with the YouTube Data API v3 enabled.
#
# Limitations:
#   - Requires YOUTUBE_API_KEY in .env. Without it, this collector is skipped.
#   - The free quota is 10,000 units/day. Each call to videos.list costs ~1 unit.
#     Hourly collection is fine; more frequent would burn quota.
#   - "Trending" videos are US-wide, not SF-specific.
#   - YouTube does not expose a public RSS feed for trending — API required.
#   - popularity_score is derived from log(viewCount + 1), capped at 10.

import math
from datetime import datetime, timezone

import requests

from config.settings import YOUTUBE_API_KEY
from db.database import get_connection, init_db

SOURCE_NAME = "youtube"
YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3/videos"


def collect() -> int:
    if not YOUTUBE_API_KEY:
        print("  YouTube: YOUTUBE_API_KEY not set — skipping.")
        return 0

    init_db()
    inserted = 0
    created_at = datetime.now(tz=timezone.utc).isoformat()

    try:
        resp = requests.get(
            YOUTUBE_API_URL,
            params={
                "part": "snippet,statistics",
                "chart": "mostPopular",
                "regionCode": "US",
                "maxResults": 25,
                "key": YOUTUBE_API_KEY,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  YouTube fetch failed: {e}")
        return 0

    with get_connection() as conn:
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            video_id = item.get("id", "")

            title = snippet.get("title", "").strip()
            if not title or not video_id:
                continue

            url = f"https://www.youtube.com/watch?v={video_id}"
            published_at = snippet.get("publishedAt", created_at)
            view_count = int(stats.get("viewCount", 0))
            popularity_score = min(math.log(view_count + 1), 10.0)

            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO stories
                    (title, url, source, timestamp, created_at, popularity_score)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (title, url, SOURCE_NAME, published_at, created_at, popularity_score),
            )
            if cursor.rowcount > 0:
                inserted += 1

        conn.commit()

    return inserted
