"""
collect_labels.py — Export human-reviewed training examples from PostgreSQL.

Run this after manually reviewing rows in training_examples (setting is_correct).
Output: training_data.json used by train_finbert.py.

Usage: python -m training.collect_labels
"""

import os, json, logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

import psycopg2

DB_CONN      = os.getenv("DB_CONNECTION", "postgresql://postgres:postgres@localhost:5433/news_market")
MIN_EXAMPLES = 30
OUTPUT_PATH  = "training_data.json"


def export_labels(output_path: str = OUTPUT_PATH) -> int:
    conn = psycopg2.connect(DB_CONN)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT headline, body, finbert_label, finbert_score, human_label, is_correct
            FROM training_examples
            WHERE is_correct IS NOT NULL
            ORDER BY created_at
        """)
        rows = cur.fetchall()

    conn.close()

    reviewed = len(rows)
    log.info(f"Found {reviewed} reviewed training examples")

    if reviewed < MIN_EXAMPLES:
        log.warning(f"Only {reviewed} labeled examples — need {MIN_EXAMPLES}+ before fine-tuning.")
        return 0

    examples = []
    for headline, body, finbert_label, score, human_label, is_correct in rows:
        # Use human_label if provided, otherwise use finbert_label when is_correct=True
        label = human_label if human_label else (finbert_label if is_correct else None)
        if label is None:
            continue  # wrong prediction but no correction given — skip

        text = ((headline or "") + " " + (body or "")).strip()
        if not text:
            continue

        examples.append({"text": text[:512], "label": label})

    with open(output_path, "w") as f:
        json.dump(examples, f, indent=2)

    dist = {}
    for ex in examples:
        dist[ex["label"]] = dist.get(ex["label"], 0) + 1

    log.info(f"Exported {len(examples)} examples to {output_path}")
    log.info(f"Label distribution: {dist}")
    return len(examples)


if __name__ == "__main__":
    n = export_labels()
    if n >= MIN_EXAMPLES:
        print(f"\nNext step: python -m training.train_finbert")
