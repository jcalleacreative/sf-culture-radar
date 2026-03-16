# backend/jobs/run_analysis.py

import json
import sys
import os

# Allow running from the backend/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import get_connection, init_db
from llm.analyzer import analyze


def main():
    init_db()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title FROM stories
            WHERE llm_score IS NULL
            ORDER BY timestamp DESC
            LIMIT 30
            """
        ).fetchall()

    if not rows:
        print("No unanalyzed stories found.")
        return

    print(f"Analyzing {len(rows)} stories...\n")

    for row in rows:
        story_id = row["id"]
        title = row["title"]
        print(f"[{story_id}] {title[:80]}")

        try:
            score, signals, category, explanation = analyze(title)
            with get_connection() as conn:
                conn.execute(
                    """
                    UPDATE stories
                    SET llm_score = ?, category = ?, explanation = ?, signals = ?
                    WHERE id = ?
                    """,
                    (score, category, explanation, json.dumps(signals), story_id),
                )
                conn.commit()
            print(f"  -> score={score}, signals={signals}, category={category}")
        except Exception as e:
            print(f"  -> ERROR: {e}")

    print("\nAnalysis complete.")


if __name__ == "__main__":
    main()
