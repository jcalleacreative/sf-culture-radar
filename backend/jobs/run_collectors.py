# backend/jobs/run_collectors.py

import sys
import os

# Allow running from the backend/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors import reddit_collector, rss_collector


def main():
    print("Running Reddit collector...")
    try:
        reddit_inserted = reddit_collector.collect()
        print(f"  Reddit: {reddit_inserted} new stories inserted")
    except Exception as e:
        print(f"  Reddit collector failed: {e}")
        reddit_inserted = 0

    print("Running RSS collector...")
    try:
        rss_inserted = rss_collector.collect()
        print(f"  RSS: {rss_inserted} new stories inserted")
    except Exception as e:
        print(f"  RSS collector failed: {e}")
        rss_inserted = 0

    total = reddit_inserted + rss_inserted
    print(f"\nDone. Total new stories inserted: {total}")


if __name__ == "__main__":
    main()
