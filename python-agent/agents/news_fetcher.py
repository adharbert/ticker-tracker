import os, logging, uuid, hashlib
from typing import Protocol, runtime_checkable
from datetime import datetime, timedelta, timezone
import yfinance as yf
import httpx

from agents.event_classifier import classify_event
from rag.chroma_store        import add_article
from utils.db                import get_watchlist, article_exists, insert_article

log = logging.getLogger(__name__)

DB_CONN      = os.getenv("DB_CONNECTION",       "postgresql://postgres:postgres@localhost/news_market")
CALLBACK_URL = os.getenv("DOTNET_CALLBACK_URL", "http://localhost:5000/api/signals/callback")
NEWS_DAYS    = int(os.getenv("NEWS_DAYS_BACK", "3"))
PROVIDER     = os.getenv("NEWS_PROVIDER", "yfinance")


# ── Normalized article model ──────────────────────────────────────────────────

class NewsArticle:
    def __init__(self, ticker, headline, body, source_name, source_url, published_at):
        self.id           = str(uuid.uuid4())
        self.ticker       = ticker
        self.headline     = headline.strip()
        self.body         = (body or "").strip()
        self.source_name  = source_name or "unknown"
        self.source_url   = source_url or ""
        self.published_at = published_at
        self.dedup_key    = hashlib.md5(
            f"{ticker}{self.headline}{published_at.date()}".encode()
        ).hexdigest()


# ── Provider protocol ─────────────────────────────────────────────────────────

@runtime_checkable
class NewsProvider(Protocol):
    def fetch(self, ticker: str, days_back: int) -> list[NewsArticle]: ...


# ── yfinance provider (default) ───────────────────────────────────────────────

class YFinanceProvider:
    def fetch(self, ticker: str, days_back: int) -> list[NewsArticle]:
        cutoff   = datetime.now(timezone.utc) - timedelta(days=days_back)
        articles = []

        try:
            news = yf.Ticker(ticker).news or []
        except Exception as e:
            log.warning(f"yfinance news fetch failed for {ticker}: {e}")
            return []

        for item in news:
            try:
                content  = item.get("content", item)
                headline = (content.get("title") or item.get("title", "")).strip()
                if not headline:
                    continue

                pub_raw = content.get("pubDate") or item.get("providerPublishTime")
                if isinstance(pub_raw, (int, float)):
                    published_at = datetime.fromtimestamp(pub_raw, tz=timezone.utc)
                elif isinstance(pub_raw, str):
                    published_at = datetime.fromisoformat(
                        pub_raw.replace("Z", "+00:00"))
                else:
                    published_at = datetime.now(timezone.utc)

                if published_at < cutoff:
                    continue

                source_name = (
                    content.get("provider", {}).get("displayName")
                    or item.get("publisher", "Yahoo Finance")
                )
                source_url = (
                    content.get("canonicalUrl", {}).get("url")
                    or item.get("link", "")
                )

                articles.append(NewsArticle(
                    ticker=ticker,
                    headline=headline,
                    body=content.get("summary", ""),
                    source_name=source_name,
                    source_url=source_url,
                    published_at=published_at,
                ))
            except Exception as e:
                log.debug(f"Skipping malformed news item for {ticker}: {e}")

        return articles


# ── Finnhub provider (optional, set NEWS_PROVIDER=finnhub + FINNHUB_API_KEY) ──

class FinnhubProvider:
    def fetch(self, ticker: str, days_back: int) -> list[NewsArticle]:
        api_key = os.getenv("FINNHUB_API_KEY")
        if not api_key:
            log.error("FINNHUB_API_KEY not set — cannot use Finnhub provider")
            return []

        from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        to_date   = datetime.now().strftime("%Y-%m-%d")

        try:
            resp = httpx.get(
                "https://finnhub.io/api/v1/company-news",
                params={"symbol": ticker, "from": from_date,
                        "to": to_date, "token": api_key},
                timeout=10,
            )
            resp.raise_for_status()
        except Exception as e:
            log.warning(f"Finnhub fetch failed for {ticker}: {e}")
            return []

        articles = []
        for item in resp.json():
            headline = item.get("headline", "").strip()
            if not headline:
                continue
            published_at = datetime.fromtimestamp(
                item.get("datetime", 0), tz=timezone.utc)
            articles.append(NewsArticle(
                ticker=ticker,
                headline=headline,
                body=item.get("summary", ""),
                source_name=item.get("source", "Finnhub"),
                source_url=item.get("url", ""),
                published_at=published_at,
            ))
        return articles


def get_provider() -> NewsProvider:
    """Return configured provider. Add new providers here."""
    if PROVIDER == "finnhub":
        return FinnhubProvider()
    return YFinanceProvider()


# ── Shared article processing ─────────────────────────────────────────────────

def _process_article(article: NewsArticle, source_tier: int, stats: dict) -> None:
    """Dedup-check, classify, and store one article. Mutates stats in place."""
    if article_exists(article.dedup_key):
        stats["skipped_dup"] += 1
        return

    event_type, _ = classify_event(article.headline, article.body)

    if event_type == "noise":
        stats["skipped_noise"] += 1
        return

    insert_article({
        "id":           article.id,
        "ticker":       article.ticker,
        "headline":     article.headline,
        "body":         article.body,
        "source_url":   article.source_url,
        "source_name":  article.source_name,
        "dedup_key":    article.dedup_key,
        "event_type":   event_type,
        "published_at": article.published_at,
    })

    add_article({
        "id":           article.id,
        "text":         article.headline + " " + article.body,
        "ticker":       article.ticker,
        "source":       article.source_name,
        "publish_date": article.published_at.strftime("%Y-%m-%d"),
        "event_type":   event_type,
        "source_tier":  source_tier,
    })

    stats["stored"] += 1
    log.info(f"Stored [{event_type}] {article.ticker}: {article.headline[:60]}")


# ── Phase 1 pipeline: fetch → classify → store (no LLM sentiment/impact yet) ─

def fetch_and_store_all() -> dict:
    """
    Phase 1 entry point. Fetches news from yfinance + RSS feeds, classifies
    events with keywords, stores in PostgreSQL and ChromaDB.
    No LLM calls, no signals generated — that is Phase 2.
    """
    from agents.rss_fetcher import fetch_rss_articles

    tickers  = get_watchlist()
    provider = get_provider()
    stats    = {"fetched": 0, "stored": 0, "skipped_noise": 0, "skipped_dup": 0}

    # Per-ticker provider (yfinance / finnhub)
    for ticker in tickers:
        articles = provider.fetch(ticker, days_back=NEWS_DAYS)
        stats["fetched"] += len(articles)
        for article in articles:
            _process_article(article, source_tier=1, stats=stats)

    # RSS feeds (runs once, matches across all tickers)
    rss_articles = fetch_rss_articles(watchlist=tickers, days_back=NEWS_DAYS)
    stats["fetched"] += len(rss_articles)
    for article in rss_articles:
        _process_article(article, source_tier=getattr(article, "source_tier", 1), stats=stats)

    log.info(f"News fetch complete: {stats}")
    return {"status": "ok", **stats}
