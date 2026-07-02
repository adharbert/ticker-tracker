import os
import logging
import psycopg2
from transformers import pipeline

log = logging.getLogger(__name__)

FINBERT_MODEL = os.getenv("FINBERT_MODEL", "ProsusAI/finbert")
DB_CONN       = os.getenv("DB_CONNECTION", "postgresql://postgres:postgres@localhost:5433/news_market")

# Loaded once at module level — first call is slow (~10s), subsequent calls are fast
_pipeline = None


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        log.info(f"Loading FinBERT model: {FINBERT_MODEL}")
        _pipeline = pipeline(
            "text-classification",
            model=FINBERT_MODEL,
            top_k=None,     # return scores for all labels (replaces deprecated return_all_scores)
        )
        log.info("FinBERT model loaded")
    return _pipeline


def score_sentiment(text: str) -> dict:
    """
    Returns sentiment scores for financial text using FinBERT.

    Result shape:
        {
            "sentiment":  "positive" | "negative" | "neutral",
            "confidence": float,          # score of dominant label
            "scores":     { label: float, ... },
            "model":      str,
        }

    FinBERT max input is 512 tokens — text is truncated to 1500 chars before
    tokenisation to stay safely within that limit.
    """
    text = text[:1500]
    pipe    = get_pipeline()
    results = pipe(text)[0]
    scores  = {r["label"]: r["score"] for r in results}

    dominant = max(scores, key=scores.get)
    return {
        "sentiment":  dominant,
        "confidence": scores[dominant],
        "scores":     scores,
        "model":      FINBERT_MODEL,
    }


def log_training_example(ticker: str, headline: str, body: str,
                          sentiment_result: dict, signal_id: str = None) -> None:
    """Log FinBERT output to training_examples for future human review and fine-tuning."""
    try:
        conn = psycopg2.connect(DB_CONN)
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO training_examples
                        (ticker, headline, body, finbert_label, finbert_score, signal_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    ticker, headline, (body or "")[:2000],
                    sentiment_result["sentiment"],
                    float(sentiment_result["confidence"]),
                    signal_id,
                ))
        conn.close()
    except Exception as e:
        log.debug(f"Could not log training example for {ticker}: {e}")
