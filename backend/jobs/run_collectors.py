# backend/jobs/run_collectors.py

import sys
import os

# Allow running from the backend/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors import (
    reddit_collector,
    rss_collector,
    google_trends_collector,
    youtube_collector,
    bluesky_collector,
)


def _run(name: str, collector_fn) -> int:
    print(f"Running {name} collector...")
    try:
        count = collector_fn()
        print(f"  {name}: {count} new stories inserted")
        return count
    except Exception as e:
        print(f"  {name} collector failed: {e}")
        return 0


def main():
    total = 0
    total += _run("Reddit", reddit_collector.collect)
    total += _run("RSS", rss_collector.collect)
    total += _run("Google Trends", google_trends_collector.collect)
    total += _run("YouTube", youtube_collector.collect)
    total += _run("BlueSky", bluesky_collector.collect)
    print(f"\nDone. Total new stories inserted: {total}")


if __name__ == "__main__":
    main()
