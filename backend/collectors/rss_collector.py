# backend/collectors/rss_collector.py

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser

from db.database import get_connection, init_db

RSS_FEEDS = {
    "Mission Local": "https://missionlocal.org/feed/",
    "SF Standard": "https://sfstandard.com/feed/",
    "SFGATE": "https://www.sfgate.com/rss/feed/SFGATE-News-Feed-703720.php",
}


def _parse_timestamp(entry) -> str:
    # Try published_parsed first (struct_time), then fall back to published string
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        return dt.isoformat()
    if hasattr(entry, "published") and entry.published:
        try:
            dt = parsedate_to_datetime(entry.published)
            return dt.isoformat()
        except Exception:
            pass
    return datetime.now(tz=timezone.utc).isoformat()


def collect() -> int:
    init_db()
    inserted = 0
    created_at = datetime.now(tz=timezone.utc).isoformat()

    with get_connection() as conn:
        for source_name, feed_url in RSS_FEEDS.items():
            feed = feedparser.parse(feed_url)

            for entry in feed.entries:
                title = entry.get("title", "").strip()
                url = entry.get("link", "").strip()

                if not title or not url:
                    continue

                timestamp = _parse_timestamp(entry)

                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO stories
                        (title, url, source, timestamp, created_at, popularity_score)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (title, url, source_name, timestamp, created_at, 1.0),
                )
                if cursor.rowcount > 0:
                    inserted += 1

        conn.commit()

    return inserted
