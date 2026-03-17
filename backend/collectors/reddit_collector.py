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
