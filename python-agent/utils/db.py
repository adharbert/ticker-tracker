import os
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
