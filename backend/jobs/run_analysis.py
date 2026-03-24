# backend/jobs/run_analysis.py

import json
import sys
import os
from datetime import datetime, timezone, timedelta

# Allow running from the backend/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import get_connection, init_db
from llm.analyzer import analyze
from config.settings import (
    ANALYSIS_TARGET_HIGH_SCORE,
    ANALYSIS_HIGH_SCORE_THRESHOLD,
    ANALYSIS_BATCH_SIZE,
    ANALYSIS_MAX_ITERATIONS,
)


def _count_high_scorers(conn, cutoff: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM stories WHERE llm_score >= ? AND timestamp >= ?",
        (ANALYSIS_HIGH_SCORE_THRESHOLD, cutoff),
    ).fetchone()
    return row[0]


def main():
    init_db()

    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=7)).isoformat()

    with get_connection() as conn:
        high_scorers = _count_high_scorers(conn, cutoff)

    if high_scorers >= ANALYSIS_TARGET_HIGH_SCORE:
        print(
            f"Already have {high_scorers} stories scoring >= {ANALYSIS_HIGH_SCORE_THRESHOLD} "
            f"in the last 7 days (target: {ANALYSIS_TARGET_HIGH_SCORE}). No analysis needed."
        )
        return

    total_analyzed = 0
    scored_this_run = 0
    offset = 0

    for iteration in range(1, ANALYSIS_MAX_ITERATIONS + 1):
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, title, url FROM stories
                WHERE llm_score IS NULL AND length(title) > 50
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (ANALYSIS_BATCH_SIZE, offset),
            ).fetchall()

        if not rows:
            print("No more unscored stories found.")
            break

        print(f"\n--- Iteration {iteration} ({len(rows)} stories) ---\n")

        for row in rows:
            story_id = row["id"]
            title = row["title"]
            print(f"[{story_id}] {title[:80]}")
            print(f"  {row['url']}")

            try:
                playable, score, signals, category, explanation = analyze(title)
                with get_connection() as conn:
                    conn.execute(
                        """
                        UPDATE stories
                        SET llm_score = ?, category = ?, explanation = ?, signals = ?, playable = ?
                        WHERE id = ?
                        """,
                        (score, category, explanation, json.dumps(signals), int(playable), story_id),
                    )
                    conn.commit()
                print(f"  -> playable={playable}, score={score}, signals={signals}, category={category}")
                total_analyzed += 1
                if score >= ANALYSIS_HIGH_SCORE_THRESHOLD:
                    scored_this_run += 1
            except Exception as e:
                print(f"  -> ERROR: {e}")

        offset += len(rows)

        with get_connection() as conn:
            high_scorers = _count_high_scorers(conn, cutoff)

        print(f"\nHigh scorers in last 7 days: {high_scorers}/{ANALYSIS_TARGET_HIGH_SCORE}")

        if high_scorers >= ANALYSIS_TARGET_HIGH_SCORE:
            print("Target reached.")
            break
    else:
        print(f"\nWarning: reached ANALYSIS_MAX_ITERATIONS ({ANALYSIS_MAX_ITERATIONS}) without hitting target.")

    print(
        f"\nDone. Analyzed {total_analyzed} stories this run. "
        f"{scored_this_run} scored >= {ANALYSIS_HIGH_SCORE_THRESHOLD}. "
        f"{high_scorers} high scorers total in the last 7 days."
    )


if __name__ == "__main__":
    main()
