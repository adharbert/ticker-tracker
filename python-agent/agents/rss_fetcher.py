"""
rss_fetcher.py — Fetch general financial RSS feeds and match articles to
watchlist tickers by scanning headline + body for ticker symbols and company names.

RSS feeds are not ticker-scoped so this module does not implement NewsProvider.
fetch_rss_articles() runs once per pipeline cycle and returns one NewsArticle
per (article × matched_ticker) pair.
"""

import logging
import os
import re
import time
import uuid
import hashlib
from calendar import timegm
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import feedparser

log = logging.getLogger(__name__)


RSS_FEEDS: list[dict] = [
    {"url": "https://feeds.reuters.com/reuters/businessNews",            "name": "Reuters",     "tier": 3},
    {"url": "https://feeds.reuters.com/reuters/companyNews",             "name": "Reuters",     "tier": 3},
    {"url": "https://www.cnbc.com/id/100003114/device/rss/rss.html",    "name": "CNBC",        "tier": 2},
    {"url": "https://www.cnbc.com/id/10001147/device/rss/rss.html",     "name": "CNBC",        "tier": 2},
    {"url": "https://feeds.marketwatch.com/marketwatch/topstories/",    "name": "MarketWatch", "tier": 2},
    {"url": "https://feeds.marketwatch.com/marketwatch/marketpulse/",   "name": "MarketWatch", "tier": 2},
    {"url": "https://finance.yahoo.com/rss/topfinstories",              "name": "Yahoo Finance","tier": 2},
    {"url": "https://finance.yahoo.com/news/rssindex",                  "name": "Yahoo Finance","tier": 2},
]

_TICKER_PATTERN = re.compile(r"\$([A-Z]{1,5})\b|\(([A-Z]{1,5})\)|\b([A-Z]{2,5})\b")

_COMPANY_NAME_MAP: dict[str, str] = {
    "apple":             "AAPL",
    "microsoft":         "MSFT",
    "amazon":            "AMZN",
    "google":            "GOOGL",
    "alphabet":          "GOOGL",
    "meta":              "META",
    "tesla":             "TSLA",
    "nvidia":            "NVDA",
    "berkshire":         "BRK-B",
    "jpmorgan":          "JPM",
    "jp morgan":         "JPM",
    "goldman":           "GS",
    "goldman sachs":     "GS",
    "morgan stanley":    "MS",
    "bank of america":   "BAC",
    "wells fargo":       "WFC",
    "exxon":             "XOM",
    "chevron":           "CVX",
    "walmart":           "WMT",
    "citigroup":         "C",
    "citi":              "C",
    "biobarin":          "BMRN",
    "spacex":            "SPCX",
    "denali":            "DNLI",
    "amphastar":         "AMPH",
    "bitcoin":           "BTC-USD",
    "btc":               "BTC-USD",
    "cryptocurrency":    "BTC-USD",
    "crypto":            "BTC-USD",
}

_EDGAR_SKIP: set[str] = {"BTC-USD", "ETH-USD"}  # non-equity tickers with no SEC filings
_EDGAR_FORMS   = ["8-K", "10-Q"]
_EDGAR_AGENT   = os.getenv("SEC_USER_AGENT", "NewsMarketAgent research@localhost.com")
_GOOGLE_NEWS_TIER = 2  # Google aggregates major outlets; resolve per-article via _TIER_MAP

_TIER_MAP: dict[str, int] = {
    "reuters":              3,
    "ap ":                  3,
    "associated press":     3,
    "cnbc":                 2,
    "marketwatch":          2,
    "bloomberg":            2,
    "yahoo finance":        2,
    "wsj":                  2,
    "wall street journal":  2,
    "financial times":      2,
}


def _find_tickers_in_text(text: str, watchlist_set: set[str]) -> set[str]:
    found: set[str] = set()
    upper_text = text.upper()

    for m in _TICKER_PATTERN.finditer(upper_text):
        candidate = m.group(1) or m.group(2) or m.group(3)
        if candidate and candidate in watchlist_set:
            found.add(candidate)

    lower_text = text.lower()
    for name, ticker in _COMPANY_NAME_MAP.items():
        if name in lower_text and ticker in watchlist_set:
            found.add(ticker)

    return found


def _parse_entry_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val is not None:
            return datetime.fromtimestamp(timegm(val), tz=timezone.utc)
    return None


def _resolve_tier(feed_tier: int, source_name: str) -> int:
    lower = source_name.lower()
    for key, tier in _TIER_MAP.items():
        if key in lower:
            return max(feed_tier, tier)
    return feed_tier


def fetch_rss_articles(watchlist: list[str], days_back: int) -> list:
    """
    Fetch all configured RSS feeds, match each article to watchlist tickers,
    and return one NewsArticle per (entry, matched_ticker) pair.
    Imports NewsArticle locally to avoid circular imports.
    """
    from agents.news_fetcher import NewsArticle

    if not watchlist:
        return []

    cutoff        = datetime.now(timezone.utc) - timedelta(days=days_back)
    watchlist_set = set(watchlist)
    results: list = []

    for feed_cfg in RSS_FEEDS:
        url       = feed_cfg["url"]
        feed_name = feed_cfg["name"]
        feed_tier = feed_cfg["tier"]

        try:
            parsed = feedparser.parse(url)
        except Exception as e:
            log.warning(f"RSS parse error for {url}: {e}")
            continue

        if parsed.bozo and parsed.bozo_exception:
            log.debug(f"RSS bozo flag for {url}: {parsed.bozo_exception}")

        for entry in parsed.entries:
            try:
                headline = (entry.get("title") or "").strip()
                if not headline:
                    continue

                body = (
                    entry.get("summary")
                    or entry.get("description")
                    or (entry.get("content") or [{}])[0].get("value", "")
                    or ""
                ).strip()

                published_at = _parse_entry_date(entry)
                if published_at is None:
                    published_at = datetime.now(timezone.utc)

                if published_at < cutoff:
                    continue

                source_url  = entry.get("link") or entry.get("id") or ""
                source_name = parsed.feed.get("title") or feed_name
                tier        = _resolve_tier(feed_tier, source_name)

                matched_tickers = _find_tickers_in_text(
                    headline + " " + body, watchlist_set)

                if not matched_tickers:
                    continue

                for ticker in matched_tickers:
                    article             = NewsArticle(
                        ticker=ticker,
                        headline=headline,
                        body=body,
                        source_name=source_name,
                        source_url=source_url,
                        published_at=published_at,
                    )
                    article.source_tier = tier
                    results.append(article)

            except Exception as e:
                log.debug(f"Skipping malformed RSS entry from {url}: {e}")

        log.info(f"RSS '{feed_name}': {len(parsed.entries)} entries parsed")

    log.info(f"RSS total: {len(results)} articles matched to watchlist tickers")
    return results


def fetch_google_news_articles(watchlist: list[str], days_back: int) -> list:
    """
    Fetch Google News RSS per ticker. Headlines arrive as "Title - Source Name"
    so we split to extract the real source and resolve its credibility tier.
    """
    from agents.news_fetcher import NewsArticle

    if not watchlist:
        return []

    cutoff  = datetime.now(timezone.utc) - timedelta(days=days_back)
    results: list = []

    for ticker in watchlist:
        search = quote(ticker.replace("-", " "))
        url    = (
            f"https://news.google.com/rss/search"
            f"?q={search}+stock&hl=en-US&gl=US&ceid=US:en"
        )
        try:
            parsed = feedparser.parse(url)
        except Exception as e:
            log.warning(f"Google News RSS error for {ticker}: {e}")
            continue

        count = 0
        for entry in parsed.entries:
            try:
                raw_title = (entry.get("title") or "").strip()
                if not raw_title:
                    continue

                published_at = _parse_entry_date(entry)
                if published_at is None:
                    published_at = datetime.now(timezone.utc)
                if published_at < cutoff:
                    continue

                # Google News titles: "Headline - Source Name"
                if " - " in raw_title:
                    parts       = raw_title.rsplit(" - ", 1)
                    headline    = parts[0].strip()
                    source_name = parts[1].strip()
                else:
                    headline    = raw_title
                    source_name = "Google News"

                tier    = _resolve_tier(_GOOGLE_NEWS_TIER, source_name)
                article = NewsArticle(
                    ticker=ticker,
                    headline=headline,
                    body="",
                    source_name=source_name,
                    source_url=entry.get("link") or "",
                    published_at=published_at,
                )
                article.source_tier = tier
                results.append(article)
                count += 1
            except Exception as e:
                log.debug(f"Skipping malformed Google News entry for {ticker}: {e}")

        log.info(f"Google News '{ticker}': {count} articles")

    log.info(f"Google News total: {len(results)} articles")
    return results


def fetch_edgar_articles(watchlist: list[str], days_back: int) -> list:
    """
    Fetch SEC EDGAR 8-K and 10-Q filings per ticker via the EDGAR Atom feed.
    Skips non-equity tickers (BTC-USD etc). Tier 3 — official company disclosures.
    SEC policy requires a descriptive User-Agent header (set SEC_USER_AGENT in .env).
    """
    from agents.news_fetcher import NewsArticle

    if not watchlist:
        return []

    cutoff  = datetime.now(timezone.utc) - timedelta(days=days_back)
    headers = {"User-Agent": _EDGAR_AGENT}
    results: list = []

    for ticker in watchlist:
        if ticker in _EDGAR_SKIP:
            continue

        for form_type in _EDGAR_FORMS:
            url = (
                f"https://www.sec.gov/cgi-bin/browse-edgar"
                f"?action=getcompany&CIK={ticker}&type={form_type}"
                f"&dateb=&owner=include&count=10&output=atom"
            )
            try:
                parsed = feedparser.parse(url, request_headers=headers)
                time.sleep(0.12)  # stay under SEC's 10 req/s limit
            except Exception as e:
                log.warning(f"EDGAR fetch error for {ticker} {form_type}: {e}")
                continue

            count = 0
            for entry in parsed.entries:
                try:
                    title = (entry.get("title") or "").strip()
                    if not title:
                        continue

                    published_at = _parse_entry_date(entry)
                    if published_at is None:
                        published_at = datetime.now(timezone.utc)
                    if published_at < cutoff:
                        continue

                    body    = entry.get("summary") or entry.get("description") or ""
                    article = NewsArticle(
                        ticker=ticker,
                        headline=f"[SEC {form_type}] {title}",
                        body=body,
                        source_name="SEC EDGAR",
                        source_url=entry.get("link") or entry.get("id") or "",
                        published_at=published_at,
                    )
                    article.source_tier = 3
                    results.append(article)
                    count += 1
                except Exception as e:
                    log.debug(f"Skipping malformed EDGAR entry for {ticker} {form_type}: {e}")

            log.info(f"EDGAR {ticker} {form_type}: {count} filings")

    log.info(f"EDGAR total: {len(results)} filings")
    return results
