# backend/collectors/bluesky_collector.py
#
# Pulls trending/popular posts from BlueSky via the public AT Protocol API.
# No authentication required for public read operations.
#
# Limitations:
#   - Uses the "What's Hot" curated feed, which is US/English-dominant but not
#     guaranteed to reflect emerging topics immediately.
#   - Post text is truncated to 280 characters; full context requires the post URL.
#   - Engagement metrics (likes, reposts) are available via a separate record fetch,
#     but this collector uses the feed response only to keep calls minimal.
#   - Like/repost counts are stored as upvotes/comments respectively.
#   - The public API has no published rate limits but may throttle aggressive polling.
#     Once or twice per day is recommended for "What's Hot" which updates slowly.

from datetime import datetime, timezone

import requests

from db.database import get_connection, init_db

SOURCE_NAME = "bluesky"

# The "What's Hot" feed is publicly accessible without credentials.
WHATS_HOT_FEED = "at://did:plc:z72i7hdynmk6r22z27h6tvur/app.bsky.feed.generator/whats-hot"
BSKY_API_URL = "https://public.api.bsky.app/xrpc/app.bsky.feed.getFeed"


def _post_url(uri: str) -> str:
    # Convert AT URI to bsky.app web URL
    # e.g. at://did:plc:xyz/app.bsky.feed.post/recordkey -> https://bsky.app/profile/did:plc:xyz/post/recordkey
    try:
        parts = uri.replace("at://", "").split("/")
        did = parts[0]
        rkey = parts[2]
        return f"https://bsky.app/profile/{did}/post/{rkey}"
    except Exception:
        return f"https://bsky.app"


def collect() -> int:
    init_db()
    inserted = 0
    created_at = datetime.now(tz=timezone.utc).isoformat()

    try:
        resp = requests.get(
            BSKY_API_URL,
            params={"feed": WHATS_HOT_FEED, "limit": 30},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  BlueSky fetch failed: {e}")
        return 0

    with get_connection() as conn:
        for feed_item in data.get("feed", []):
            post = feed_item.get("post", {})
            record = post.get("record", {})

            text = record.get("text", "").strip()
            if not text:
                continue

            uri = post.get("uri", "")
            url = _post_url(uri) if uri else ""
            if not url:
                continue

            created_raw = record.get("createdAt", created_at)
            like_count = post.get("likeCount", 0) or 0
            repost_count = post.get("repostCount", 0) or 0

            # Use first 120 chars of post text as title (posts have no separate title)
            title = text[:120] + ("…" if len(text) > 120 else "")

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
                    created_raw,
                    created_at,
                    like_count,
                    repost_count,
                    1.0,
                ),
            )
            if cursor.rowcount > 0:
                inserted += 1

        conn.commit()

    return inserted
