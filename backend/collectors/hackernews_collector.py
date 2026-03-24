# backend/collectors/hackernews_collector.py
#
# Pulls top stories from Hacker News via the official Firebase API.
# No API key required.
#
# Limitations:
#   - Fetches top 50 story IDs then one request per item — 50 HTTP calls per run.
#     A 0.05s delay between item fetches keeps load polite.
#   - Ask HN / text posts (no url field) are skipped.
#   - Results are global tech/startup news, not SF-specific.
#   - popularity_score = log(score + 1) + log(descendants + 1)

import math
import time
from datetime import datetime, timezone

import requests

from db.database import get_connection, init_db

SOURCE_NAME = "hackernews"
HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{id}.json"


def collect() -> int:
    init_db()
    inserted = 0
    created_at = datetime.now(tz=timezone.utc).isoformat()

    try:
        resp = requests.get(HN_TOP_URL, timeout=15)
        resp.raise_for_status()
        story_ids = resp.json()[:50]
    except Exception as e:
        print(f"  Hacker News: failed to fetch top stories: {e}")
        return 0

    with get_connection() as conn:
        for story_id in story_ids:
            try:
                item_resp = requests.get(
                    HN_ITEM_URL.format(id=story_id), timeout=15
                )
                item_resp.raise_for_status()
                item = item_resp.json()
            except Exception as e:
                print(f"  Hacker News: failed to fetch item {story_id}: {e}")
                time.sleep(0.05)
                continue

            if not item or item.get("type") != "story":
                time.sleep(0.05)
                continue

            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()

            if not title or not url:
                time.sleep(0.05)
                continue

            score = item.get("score") or 0
            descendants = item.get("descendants") or 0
            unix_time = item.get("time")
            timestamp = (
                datetime.fromtimestamp(unix_time, tz=timezone.utc).isoformat()
                if unix_time
                else created_at
            )
            popularity_score = math.log(score + 1) + math.log(descendants + 1)

            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO stories
                    (title, url, source, timestamp, created_at,
                     upvotes, comments, popularity_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    url,
                    SOURCE_NAME,
                    timestamp,
                    created_at,
                    score,
                    descendants,
                    popularity_score,
                ),
            )
            if cursor.rowcount > 0:
                inserted += 1

            time.sleep(0.05)

        conn.commit()

    return inserted
