import os
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONN = os.getenv("DB_CONNECTION", "postgresql://postgres:postgres@localhost/news_market")


def get_connection():
    return psycopg2.connect(DB_CONN)


def get_watchlist() -> list[str]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT ticker FROM watchlist ORDER BY ticker")
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def article_exists(dedup_key: str) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM news_articles WHERE dedup_key = %s", (dedup_key,))
            return cur.fetchone() is not None
    finally:
        conn.close()


def insert_signal(signal: dict, article_id: str, ticker: str, published_at) -> None:
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO signals
                        (id, ticker, article_id, event_type, sentiment, confidence,
                         impact_summary, time_horizon, source_citations,
                         uncertainty_factors, disclaimer, governance_passed,
                         source_credibility_tier, alert_suppressed,
                         requires_human_review, governance_warnings,
                         published_at, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                """, (
                    str(uuid.uuid4()), ticker, article_id,
                    signal.get("event_type", "other"),
                    signal.get("sentiment", "neutral"),
                    float(signal.get("confidence", 0)),
                    signal.get("impact_summary", ""),
                    signal.get("time_horizon", "days"),
                    signal.get("source_citations", []),
                    signal.get("uncertainty_factors", []),
                    signal.get("disclaimer", ""),
                    signal.get("governance_passed", False),
                    int(signal.get("source_credibility_tier", 1)),
                    signal.get("alert_suppressed", False),
                    signal.get("requires_human_review", False),
                    signal.get("governance_warnings", []),
                    published_at,
                ))
    finally:
        conn.close()


def insert_article(article: dict) -> None:
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO news_articles
                        (id, ticker, headline, body, source_url, source_name,
                         dedup_key, event_type, published_at, ingested_at, processed)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), FALSE)
                    ON CONFLICT (dedup_key) DO NOTHING
                """, (
                    article["id"], article["ticker"], article["headline"],
                    article.get("body", ""), article.get("source_url", ""),
                    article.get("source_name", "unknown"),
                    article["dedup_key"], article.get("event_type", "other"),
                    article["published_at"],
                ))
    finally:
        conn.close()
