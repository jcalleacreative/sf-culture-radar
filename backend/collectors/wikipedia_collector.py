# backend/collectors/wikipedia_collector.py
#
# Pulls the most-viewed Wikipedia articles for yesterday via the official
# Wikimedia Pageviews API. No API key required.
#
# Limitations:
#   - Uses yesterday's date because the current day's data is not always available.
#   - Results are global pageview data, not SF-specific.
#   - popularity_score = log(views + 1), uncapped.
#   - upvotes field stores raw view count; comments is NULL.

import math
from datetime import datetime, timezone, timedelta

import requests

from db.database import get_connection, init_db

SOURCE_NAME = "wikipedia"

SKIP_ARTICLES = {
    "Main_Page", "Special:Search", "Wikipedia:Featured_pictures",
    "-", "Special:Statistics", "Special:Export", "Special:RecentChanges",
}

PAGEVIEWS_URL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/top"
    "/en.wikipedia/all-access/{year}/{month}/{day}"
)


def collect() -> int:
    init_db()
    inserted = 0

    yesterday = datetime.now(tz=timezone.utc) - timedelta(days=1)
    year = yesterday.strftime("%Y")
    month = yesterday.strftime("%m")
    day = yesterday.strftime("%d")
    timestamp = yesterday.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    created_at = datetime.now(tz=timezone.utc).isoformat()

    url = PAGEVIEWS_URL.format(year=year, month=month, day=day)

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "sf-sketch-radar/1.0"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  Wikipedia: failed to fetch pageviews: {e}")
        return 0

    articles = data.get("items", [{}])[0].get("articles", [])

    kept = 0
    with get_connection() as conn:
        for article in articles:
            if kept >= 50:
                break

            article_key = article.get("article", "")
            if article_key in SKIP_ARTICLES:
                continue

            title = article_key.replace("_", " ")
            article_url = f"https://en.wikipedia.org/wiki/{article_key}"
            views = article.get("views") or 0
            popularity_score = math.log(views + 1)

            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO stories
                    (title, url, source, timestamp, created_at,
                     upvotes, popularity_score)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    article_url,
                    SOURCE_NAME,
                    timestamp,
                    created_at,
                    views,
                    popularity_score,
                ),
            )
            if cursor.rowcount > 0:
                inserted += 1
            kept += 1

        conn.commit()

    return inserted
