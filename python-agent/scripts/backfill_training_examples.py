"""
backfill_training_examples.py — Re-run FinBERT on all existing governance-passed
articles and populate training_examples for human review and fine-tuning.

This is a one-time script for articles processed before training_examples logging
was added. Safe to re-run — skips articles already in training_examples.

Usage: python -m scripts.backfill_training_examples
"""

import os, logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

import psycopg2
from psycopg2.extras import RealDictCursor
from agents.sentiment_agent import score_sentiment

DB_CONN = os.getenv("DB_CONNECTION", "postgresql://postgres:postgres@localhost:5433/news_market")


def run():
    conn = psycopg2.connect(DB_CONN)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT s.id AS signal_id, s.ticker,
                   n.headline, n.body
            FROM signals s
            JOIN news_articles n ON n.id = s.article_id
            WHERE s.governance_passed = TRUE
              AND n.headline IS NOT NULL
              AND s.id NOT IN (
                  SELECT signal_id FROM training_examples
                  WHERE signal_id IS NOT NULL
              )
            ORDER BY n.published_at
        """)
        rows = cur.fetchall()

    log.info(f"Backfilling {len(rows)} articles into training_examples...")

    inserted = 0
    skipped  = 0

    for row in rows:
        text = (row["headline"] or "") + " " + (row["body"] or "")
        try:
            result = score_sentiment(text)
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO training_examples
                            (ticker, headline, body, finbert_label, finbert_score, signal_id)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                    """, (
                        row["ticker"],
                        row["headline"],
                        (row["body"] or "")[:2000],
                        result["sentiment"],
                        float(result["confidence"]),
                        str(row["signal_id"]),
                    ))
            inserted += 1
            if inserted % 10 == 0:
                log.info(f"  {inserted}/{len(rows)} done...")
        except Exception as e:
            log.warning(f"Skipping signal {row['signal_id']}: {e}")
            skipped += 1

    conn.close()
    log.info(f"Backfill complete: {inserted} inserted, {skipped} skipped")
    log.info("Next step: open training_examples in DB and set is_correct = TRUE/FALSE for each row.")
    log.info("Then run: python -m training.collect_labels")


if __name__ == "__main__":
    run()
