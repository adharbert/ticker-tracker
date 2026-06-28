import os
import logging
from transformers import pipeline

log = logging.getLogger(__name__)

FINBERT_MODEL = os.getenv("FINBERT_MODEL", "ProsusAI/finbert")

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
