import os, logging, uuid, hashlib
from typing import Protocol, runtime_checkable
from datetime import datetime, timedelta, timezone
import yfinance as yf
import httpx

from agents.event_classifier import classify_event
from agents.sentiment_agent  import score_sentiment
from agents.impact_reasoner  import analyze_impact
from rag.chroma_store        import add_article, query_recent
from governance.guardrails   import validate_signal
from utils.ollama_client     import OllamaClient
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


# ── Phase 2 pipeline: sentiment + impact + governance ─────────────────────────

def process_article(article: NewsArticle, ollama: OllamaClient) -> dict:
    """
    Run one article through the full AI pipeline.
    Returns a callback payload dict.
    Caller is responsible for dedup-check and DB insert before calling this.
    """
    text = article.headline + " " + article.body

    event_type, _ = classify_event(article.headline, article.body)
    if event_type == "noise":
        log.info(f"Signal NOISE {article.ticker}: {article.headline[:80]}")
        return {
            "articleId": article.id, "ticker": article.ticker,
            "governancePassed": False, "rejectionReason": "noise", "signal": None,
        }

    sentiment   = score_sentiment(text)
    rag_results = query_recent(article.headline, ticker=article.ticker,
                               days_back=30, n_results=5)
    rag_context = rag_results.get("documents", [[]])[0]

    raw_signal = analyze_impact(
        {"event_type": event_type, "headline": article.headline,
         "tickers": [article.ticker]},
        sentiment, rag_context, ollama,
    )

    result = validate_signal(raw_signal, sources=[article.source_name])

    if result.passed:
        log.info(f"Signal PASSED [{raw_signal.get('event_type')}] {article.ticker}: "
                 f"confidence={raw_signal.get('confidence'):.2f} warnings={result.warnings}")
        add_article({
            "id":           article.id,
            "text":         text,
            "ticker":       article.ticker,
            "source":       article.source_name,
            "publish_date": article.published_at.strftime("%Y-%m-%d"),
            "event_type":   event_type,
            "source_tier":  result.signal.get("source_credibility_tier", 1),
        })

    if not result.passed:
        log.info(f"Signal REJECTED [{raw_signal.get('event_type', '?')}] {article.ticker}: "
                 f"{result.rejection_reason}")

    return {
        "articleId":        article.id,
        "ticker":           article.ticker,
        "governancePassed": result.passed,
        "rejectionReason":  result.rejection_reason,
        "signal":           result.signal,
    }


def fetch_and_process_all() -> dict:
    """
    Phase 2 entry point. Fetches news, runs full AI pipeline (sentiment + impact +
    governance), stores signals, and sends callback to .NET API.
    """
    import httpx
    from agents.rss_fetcher import fetch_rss_articles, fetch_google_news_articles, fetch_edgar_articles

    tickers  = get_watchlist()
    provider = get_provider()
    ollama   = OllamaClient()
    stats    = {"fetched": 0, "processed": 0, "passed": 0, "rejected": 0}

    def _run(article: NewsArticle, source_tier: int) -> None:
        try:
            if article_exists(article.dedup_key):
                return
            insert_article({
                "id":           article.id,
                "ticker":       article.ticker,
                "headline":     article.headline,
                "body":         article.body,
                "source_url":   article.source_url,
                "source_name":  article.source_name,
                "dedup_key":    article.dedup_key,
                "published_at": article.published_at,
            })
            payload = process_article(article, ollama)
            stats["processed"] += 1
            if payload["governancePassed"]:
                stats["passed"] += 1
            else:
                stats["rejected"] += 1
            try:
                httpx.post(CALLBACK_URL, json=payload, timeout=10)
            except Exception as e:
                log.warning(f"Callback failed for {article.id}: {e}")
        except Exception as e:
            log.warning(f"Skipping article [{article.ticker}] '{article.headline[:60]}': {e}")
            stats["rejected"] += 1

    for ticker in tickers:
        articles = provider.fetch(ticker, days_back=NEWS_DAYS)
        stats["fetched"] += len(articles)
        for article in articles:
            _run(article, source_tier=1)

    rss_articles = fetch_rss_articles(watchlist=tickers, days_back=NEWS_DAYS)
    stats["fetched"] += len(rss_articles)
    for article in rss_articles:
        _run(article, source_tier=getattr(article, "source_tier", 1))

    google_articles = fetch_google_news_articles(watchlist=tickers, days_back=NEWS_DAYS)
    stats["fetched"] += len(google_articles)
    for article in google_articles:
        _run(article, source_tier=getattr(article, "source_tier", 2))

    edgar_articles = fetch_edgar_articles(watchlist=tickers, days_back=NEWS_DAYS)
    stats["fetched"] += len(edgar_articles)
    for article in edgar_articles:
        _run(article, source_tier=getattr(article, "source_tier", 3))

    log.info(f"Phase 2 ingest complete: {stats}")
    return {"status": "ok", **stats}
