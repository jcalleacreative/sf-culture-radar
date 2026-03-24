# backend/collectors/google_trends_collector.py
#
# Uses the unofficial pytrends library to pull rising/trending search queries
# from Google Trends. No API key required.
#
# Limitations:
#   - pytrends is an unofficial wrapper and may break if Google changes their API.
#   - Google rate-limits heavily; running this too frequently will result in 429 errors.
#     Once per day is recommended.
#   - Results are US-wide trending queries, not SF-specific.
#   - Topics stored as individual items with no upvotes/comments.

import time
from datetime import datetime, timezone

from pytrends.request import TrendReq

from db.database import get_connection, init_db

SOURCE_NAME = "google_trends"

# pytrends raises ResponseError (a subclass of Exception) on HTTP errors.
# 429 responses mean Google is rate-limiting. Back off and retry a few times,
# then give up — the collector failing silently is acceptable since it's unreliable.
_RETRIES = 3
_BACKOFF_START = 30  # seconds


def _fetch_with_retry():
    backoff = _BACKOFF_START
    last_err = None
    for attempt in range(_RETRIES):
        try:
            pytrends = TrendReq(hl="en-US", tz=360, timeout=(10, 25))
            return pytrends.realtime_trending_searches(pn="US")
        except Exception as e:
            last_err = e
            err_str = str(e)
            if "429" in err_str or "Too Many Requests" in err_str:
                if attempt < _RETRIES - 1:
                    print(f"  Google Trends: rate-limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    backoff *= 2
                else:
                    print(
                        f"  Google Trends: rate-limited after {_RETRIES} attempts. "
                        "Consider reducing collection frequency to once per day."
                    )
            else:
                # Non-rate-limit error — no point retrying
                break
    raise last_err


def collect() -> int:
    init_db()
    inserted = 0

    try:
        trending_df = _fetch_with_retry()
    except Exception as e:
        print(f"  Google Trends fetch failed: {e}")
        return 0

    created_at = datetime.now(tz=timezone.utc).isoformat()
    timestamp = created_at  # Trends don't carry a publish timestamp

    with get_connection() as conn:
        for _, row in trending_df.iterrows():
            title = str(row.get("title", "")).strip()
            if not title:
                continue

            # Use a stable URL pointing to Google Trends for this query
            url = f"https://trends.google.com/trends/explore?q={title.replace(' ', '+')}&geo=US"

            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO stories
                    (title, url, source, timestamp, created_at, popularity_score)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (title, url, SOURCE_NAME, timestamp, created_at, 1.0),
            )
            if cursor.rowcount > 0:
                inserted += 1

        conn.commit()

    return inserted
