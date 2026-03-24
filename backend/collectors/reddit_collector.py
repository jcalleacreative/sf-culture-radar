# backend/collectors/reddit_collector.py

import math
import time
from datetime import datetime, timezone

import praw
import prawcore

from config.settings import (
    REDDIT_CLIENT_ID,
    REDDIT_CLIENT_SECRET,
    REDDIT_USER_AGENT,
    REDDIT_POST_LIMIT,
)
from db.database import get_connection, init_db

SUBREDDITS = ["sanfrancisco", "AskSF", "bayarea", "technology"]

# r/technology is US-wide. Only ingest posts that have a clear SF/Bay Area angle.
TECHNOLOGY_SF_KEYWORDS = [
    "san francisco", "sf ", "bay area", "silicon valley",
    "oakland", "berkeley", "soma", "mission district",
    "caltrain", "bart ", "waymo", "openai", "anthropic",
    "google", "apple", "meta", "salesforce", "twitter", "x.com",
]


def _passes_subreddit_filter(sub_name: str, title: str) -> bool:
    """Return False to skip a post that doesn't meet subreddit-specific criteria."""
    if sub_name == "technology":
        lower = title.lower()
        return any(kw in lower for kw in TECHNOLOGY_SF_KEYWORDS)
    return True


def _make_reddit() -> praw.Reddit:
    return praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT,
    )


def _fetch_posts_with_retry(subreddit, limit: int) -> list:
    backoff = 2
    for attempt in range(5):
        try:
            posts = list(subreddit.hot(limit=limit))
            return posts
        except prawcore.exceptions.TooManyRequests:
            if attempt == 4:
                raise
            print(f"Rate limited by Reddit. Retrying in {backoff}s...")
            time.sleep(backoff)
            backoff *= 2
    return []


def collect() -> int:
    init_db()
    reddit = _make_reddit()
    inserted = 0

    with get_connection() as conn:
        for sub_name in SUBREDDITS:
            subreddit = reddit.subreddit(sub_name)
            posts = _fetch_posts_with_retry(subreddit, REDDIT_POST_LIMIT)

            for post in posts:
                if not _passes_subreddit_filter(sub_name, post.title):
                    continue
                upvotes = post.score
                comments = post.num_comments
                popularity_score = math.log(upvotes + 1) + math.log(comments + 1)

                timestamp = datetime.fromtimestamp(
                    post.created_utc, tz=timezone.utc
                ).isoformat()
                created_at = datetime.now(tz=timezone.utc).isoformat()

                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO stories
                        (title, url, source, timestamp, created_at,
                         upvotes, comments, popularity_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        post.title,
                        f"https://www.reddit.com{post.permalink}",
                        sub_name,
                        timestamp,
                        created_at,
                        upvotes,
                        comments,
                        popularity_score,
                    ),
                )
                if cursor.rowcount > 0:
                    inserted += 1

        conn.commit()

    return inserted
