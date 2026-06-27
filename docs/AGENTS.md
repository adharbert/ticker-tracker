# AI Agents — Python Service Specification

> Claude Code: implement all files in `python-agent/` using this spec.
> Read `docs/ARCHITECTURE.md` first for the full pipeline context.
> Build governance/guardrails.py BEFORE wiring up impact_reasoner outputs.

---

## Project setup

```bash
cd python-agent
python -m venv .venv && source .venv/Scripts/activate  # Windows: Scripts
pip install -r requirements.txt
```

### `requirements.txt`

```
# AI / ML
transformers==4.41.2
torch==2.3.1                  # CPU-only for FinBERT if no GPU: pip install torch --index-url https://download.pytorch.org/whl/cpu
sentence-transformers==3.0.1  # ChromaDB embeddings

# Data
pandas==2.2.2
yfinance                      # news headlines + OHLCV prices (free, no key) — pin after upgrade
psycopg2-binary==2.9.9

# HTTP
httpx==0.27.0                 # Ollama + callback
feedparser==6.0.11            # RSS feed ingestion (Phase 1)

# Web server (HTTP trigger endpoint)
flask==3.0.3                  # C# calls POST /trigger

# Scheduling
apscheduler==3.10.4           # daily ingest cron

# Vector DB
chromadb==0.5.3

# Config
python-dotenv==1.0.1
```

> **Note:** `yfinance==0.2.40` returns empty responses from Yahoo Finance as of mid-2026.
> Run `pip install --upgrade yfinance` and pin the installed version after upgrading.
> `pika` (RabbitMQ) is not used in Phase 1 — the pipeline is HTTP-triggered, not queue-driven.

---

## File: `python-agent/main.py`

Entry point — runs three things in parallel:
1. Daily scheduler (APScheduler) triggers news ingest at configured time
2. Flask HTTP server on port 5001 lets C# trigger a manual ingest
3. News pipeline runs in the main thread when triggered

```python
import os, logging, threading
from dotenv import load_dotenv
from flask import Flask, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

PORT          = int(os.getenv("PYTHON_AGENT_PORT", 5001))
SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "07:00")

app = Flask(__name__)
_pipeline_lock = threading.Lock()    # prevent concurrent ingest runs


def run_ingest_pipeline():
    """Fetch news and run the full agent pipeline. Called by scheduler and HTTP trigger."""
    if not _pipeline_lock.acquire(blocking=False):
        log.info("Ingest already running — skipping")
        return {"status": "already_running"}

    try:
        from agents.news_fetcher import fetch_and_process_all
        result = fetch_and_process_all()
        log.info(f"Ingest complete: {result}")
        return result
    except Exception as e:
        log.error(f"Ingest pipeline failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
    finally:
        _pipeline_lock.release()


@app.route("/trigger", methods=["POST"])
def trigger():
    """Called by C# IngestController to trigger a manual ingest."""
    thread = threading.Thread(target=run_ingest_pipeline, daemon=True)
    thread.start()
    return jsonify({"status": "triggered"}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


def start_scheduler():
    hour, minute = SCHEDULE_TIME.split(":")
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_ingest_pipeline, "cron",
                      day_of_week="mon-fri",
                      hour=int(hour), minute=int(minute))
    scheduler.start()
    log.info(f"Scheduler started — daily ingest at {SCHEDULE_TIME} (Mon-Fri)")
    return scheduler


if __name__ == "__main__":
    scheduler = start_scheduler()

    log.info(f"Python agent HTTP server starting on port {PORT}")
    log.info("C# can trigger ingest via: POST http://localhost:{PORT}/trigger")

    # Run Flask (blocking) — scheduler runs in background thread
    app.run(host="0.0.0.0", port=PORT, debug=False)
```

---

## File: `python-agent/agents/news_fetcher.py` {#news-provider-abstraction}

Fetches news headlines using a pluggable provider. Default is yfinance (free, no key).
To add a new provider (Finnhub, Alpha Vantage, Polygon.io, etc.), implement the
`NewsProvider` protocol and add a branch in `get_provider()`.

```python
import os, logging, uuid, hashlib
from typing import Protocol
from datetime import datetime, timedelta, timezone
import yfinance as yf
import psycopg2
import httpx

from agents.event_classifier import classify_event
from agents.sentiment_agent  import score_sentiment
from agents.impact_reasoner  import analyze_impact
from rag.chroma_store        import add_article, query_recent
from governance.guardrails   import validate_signal
from utils.ollama_client     import OllamaClient

log = logging.getLogger(__name__)

DB_CONN      = os.getenv("DB_CONNECTION",       "postgresql://postgres:postgres@localhost/news_market")
CALLBACK_URL = os.getenv("DOTNET_CALLBACK_URL", "http://localhost:5000/api/signals/callback")
NEWS_DAYS    = int(os.getenv("NEWS_DAYS_BACK", 3))
PROVIDER     = os.getenv("NEWS_PROVIDER", "yfinance")


# ── Provider protocol ─────────────────────────────────────────────────────────

class NewsArticle:
    """Normalized news article across all providers."""
    def __init__(self, ticker, headline, body, source_name, source_url, published_at):
        self.id           = str(uuid.uuid4())
        self.ticker       = ticker
        self.headline     = headline
        self.body         = body or ""
        self.source_name  = source_name or "unknown"
        self.source_url   = source_url or ""
        self.published_at = published_at
        # Stable dedup key: hash of ticker + headline + date
        self.dedup_key    = hashlib.md5(
            f"{ticker}{headline}{published_at.date()}".encode()
        ).hexdigest()


class NewsProvider(Protocol):
    def fetch(self, ticker: str, days_back: int) -> list[NewsArticle]: ...


# ── yfinance provider (default — free, no key) ────────────────────────────────

class YFinanceProvider:
    def fetch(self, ticker: str, days_back: int) -> list[NewsArticle]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        articles = []

        try:
            t    = yf.Ticker(ticker)
            news = t.news or []
        except Exception as e:
            log.warning(f"yfinance news fetch failed for {ticker}: {e}")
            return []

        for item in news:
            try:
                # yfinance returns different shapes across versions — handle both
                content = item.get("content", item)      # v0.2.x wraps in "content"

                headline = (content.get("title")
                            or item.get("title", "")).strip()
                if not headline:
                    continue

                # Published time: ISO string or Unix timestamp
                pub_raw = (content.get("pubDate")
                           or item.get("providerPublishTime"))
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
                body = content.get("summary", "")

                articles.append(NewsArticle(
                    ticker=ticker, headline=headline, body=body,
                    source_name=source_name, source_url=source_url,
                    published_at=published_at,
                ))
            except Exception as e:
                log.debug(f"Skipping malformed news item for {ticker}: {e}")

        return articles


# ── Provider registry (add new providers here) ────────────────────────────────

def get_provider() -> NewsProvider:
    """
    Returns the configured news provider.
    Add new providers by implementing NewsProvider and adding a branch here.

    Supported values for NEWS_PROVIDER env var:
      yfinance   — free, no API key, default
      finnhub    — requires FINNHUB_API_KEY env var (free tier available)
    """
    if PROVIDER == "finnhub":
        return FinnhubProvider()
    return YFinanceProvider()      # default


class FinnhubProvider:
    """Finnhub news provider — set NEWS_PROVIDER=finnhub and FINNHUB_API_KEY in .env"""
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
                params={"symbol": ticker, "from": from_date, "to": to_date,
                        "token": api_key},
                timeout=10,
            )
            resp.raise_for_status()
            items = resp.json()
        except Exception as e:
            log.warning(f"Finnhub fetch failed for {ticker}: {e}")
            return []

        articles = []
        for item in items:
            headline = item.get("headline", "").strip()
            if not headline:
                continue
            published_at = datetime.fromtimestamp(
                item.get("datetime", 0), tz=timezone.utc)
            articles.append(NewsArticle(
                ticker=ticker, headline=headline,
                body=item.get("summary", ""),
                source_name=item.get("source", "Finnhub"),
                source_url=item.get("url", ""),
                published_at=published_at,
            ))
        return articles


# ── Pipeline ──────────────────────────────────────────────────────────────────

def process_article(article: NewsArticle, ollama: OllamaClient) -> dict:
    """Run one article through the full agent pipeline. Returns callback payload."""
    text = article.headline + " " + article.body

    event_type, _ = classify_event(article.headline, article.body)
    if event_type == "noise":
        return {"articleId": article.id, "ticker": article.ticker,
                "governancePassed": False, "rejectionReason": "noise", "signal": None}

    sentiment   = score_sentiment(text)
    rag_results = query_recent(article.headline, ticker=article.ticker,
                               days_back=30, n_results=5)
    rag_context = rag_results.get("documents", [[]])[0]

    raw_signal = analyze_impact(
        {"event_type": event_type, "headline": article.headline, "tickers": [article.ticker]},
        sentiment, rag_context, ollama,
    )

    result = validate_signal(raw_signal, sources=[article.source_name])

    if result.passed:
        add_article({
            "id":           article.id,
            "text":         text,
            "ticker":       article.ticker,
            "source":       article.source_name,
            "publish_date": article.published_at.strftime("%Y-%m-%d"),
            "event_type":   event_type,
            "source_tier":  result.signal.get("source_credibility_tier", 1),
        })

    return {
        "articleId":        article.id,
        "ticker":           article.ticker,
        "governancePassed": result.passed,
        "rejectionReason":  result.rejection_reason,
        "signal":           result.signal,
    }


def fetch_and_process_all() -> dict:
    """
    Main entry point called by scheduler and HTTP trigger.
    Fetches news for all watchlist tickers, runs pipeline, callbacks to C#.
    """
    conn     = psycopg2.connect(DB_CONN)
    provider = get_provider()
    ollama   = OllamaClient()

    with conn.cursor() as cur:
        cur.execute("SELECT ticker FROM watchlist")
        tickers = [row[0] for row in cur.fetchall()]

    stats = {"fetched": 0, "processed": 0, "passed": 0, "rejected": 0}

    for ticker in tickers:
        articles = provider.fetch(ticker, days_back=NEWS_DAYS)
        stats["fetched"] += len(articles)

        for article in articles:
            # Dedup: skip articles already in DB
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM news_articles WHERE dedup_key = %s",
                    (article.dedup_key,))
                if cur.fetchone():
                    continue

            # Store article
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO news_articles
                            (id, ticker, headline, body, source_url, source_name,
                             dedup_key, published_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (article.id, article.ticker, article.headline,
                          article.body, article.source_url, article.source_name,
                          article.dedup_key, article.published_at))

            # Run pipeline + callback
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

    conn.close()
    log.info(f"Ingest stats: {stats}")
    return {"status": "ok", **stats}
```

---

## File: `python-agent/agents/rss_fetcher.py` (Phase 1 addition)

Fetches 8 general financial RSS feeds and matches articles to watchlist tickers.
Runs once per pipeline cycle alongside the per-ticker yfinance provider.

Key design points:
- Does **not** implement `NewsProvider` — RSS is not ticker-scoped, so it cannot follow
  the `fetch(ticker, days_back)` protocol. Called directly from `fetch_and_store_all()`.
- `_find_tickers_in_text()` — regex for `$AAPL`, `(AAPL)`, bare `AAPL` word boundaries,
  plus a company name map for prose mentions (e.g. "Citigroup" → C).
- One `NewsArticle` per (entry × matched_ticker). Dedup keys differ per ticker so the
  same headline stored for two tickers becomes two independent RAG documents.
- Source tiers: Reuters/AP = 3, CNBC/MarketWatch/Yahoo Finance/Bloomberg = 2, unknown = 1.
- Sets `article.source_tier` as a dynamic attribute; `_process_article()` reads it via `getattr`.

Feeds configured:
- Reuters Business + Companies (tier 3)
- CNBC Top News + Finance (tier 2)
- MarketWatch Top Stories + MarketPulse (tier 2)
- Yahoo Finance Top Financial + News (tier 2)

---

## File: `python-agent/agents/price_fetcher.py`

Fetches daily OHLCV for watchlist tickers and stores in PostgreSQL.
Called by a cron job or manually before backtesting.

```python
import os, logging
import yfinance as yf
import psycopg2
from datetime import datetime, timedelta

log = logging.getLogger(__name__)
DB_CONN = os.getenv("DB_CONNECTION", "postgresql://postgres:postgres@localhost/news_market")


def fetch_prices(tickers: list[str] = None, days_back: int = 30):
    """Fetch daily OHLCV for each ticker and upsert into prices table."""
    conn  = psycopg2.connect(DB_CONN)
    end   = datetime.today()
    start = end - timedelta(days=days_back)

    if tickers is None:
        with conn.cursor() as cur:
            cur.execute("SELECT ticker FROM watchlist")
            tickers = [row[0] for row in cur.fetchall()]

    for ticker in tickers:
        try:
            df = yf.download(ticker, start=start, end=end, progress=False)
            df.reset_index(inplace=True)
            with conn:
                with conn.cursor() as cur:
                    for _, row in df.iterrows():
                        cur.execute("""
                            INSERT INTO prices (ticker, date, open, high, low, close, volume)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (ticker, date) DO UPDATE
                            SET close = EXCLUDED.close, volume = EXCLUDED.volume
                        """, (ticker, row["Date"].date(),
                              float(row["Open"]),  float(row["High"]),
                              float(row["Low"]),   float(row["Close"]),
                              int(row["Volume"])))
            log.info(f"Prices fetched for {ticker}: {len(df)} days")
        except Exception as e:
            log.error(f"Failed to fetch prices for {ticker}: {e}")

    conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fetch_prices()
```

---

## File: `python-agent/agents/event_classifier.py`

**Phase 1:** keyword-based (fast, no GPU, no Ollama dependency).
**Phase 2:** upgrade to Ollama LLM classification by replacing `classify_event()`.

```python
import os, logging
from utils.ollama_client import OllamaClient

log = logging.getLogger(__name__)

EVENT_KEYWORDS = {
    "fed_rate":   ["federal reserve", "fed", "rate hike", "rate cut", "fomc",
                   "interest rate", "powell", "basis points", "bps", "monetary policy"],
    "earnings":   ["earnings", "eps", "revenue", "beats", "misses", "guidance",
                   "quarterly", "q1", "q2", "q3", "q4", "annual results", "profit"],
    "merger":     ["merger", "acquisition", "takeover", "buyout", "deal",
                   "acquired", "acquires", "merge", "tender offer"],
    "regulatory": ["sec", "ftc", "doj", "antitrust", "fine", "penalty",
                   "investigation", "subpoena", "regulation", "compliance", "lawsuit"],
    "macro":      ["cpi", "inflation", "gdp", "unemployment", "jobs report",
                   "nonfarm", "pce", "treasury", "yield", "recession", "debt ceiling"],
}

CLASSIFIER_SYSTEM_PROMPT = """
You are a financial news event classifier. Classify the news into exactly one category.

Categories: fed_rate | earnings | merger | regulatory | macro | other | noise

RULES:
- Return ONLY a JSON object. No explanation, no markdown.
- "noise" means the article has no clear market-moving event.
- Choose the single most relevant category.

Output format:
{"event_type": "earnings", "confidence": 0.9, "reasoning": "Article discusses Q3 EPS beat"}
"""


def classify_event(headline: str, body: str = "") -> tuple[str, float]:
    """
    Phase 1: keyword-based classification.
    Returns (event_type, confidence_score).
    """
    text   = (headline + " " + body).lower()
    scores = {}

    for event_type, keywords in EVENT_KEYWORDS.items():
        matches = sum(1 for kw in keywords if kw in text)
        if matches > 0:
            scores[event_type] = matches / len(keywords)

    if not scores:
        return "noise", 0.0

    best = max(scores, key=scores.get)
    if scores[best] < 0.05:
        return "noise", scores[best]

    return best, min(scores[best] * 10, 1.0)


def classify_event_llm(headline: str, body: str = "",
                        ollama: OllamaClient = None) -> tuple[str, float]:
    """
    Phase 2: LLM-based classification via Ollama.
    More accurate for nuanced headlines. Swap in for classify_event() in Phase 2.
    """
    if ollama is None:
        ollama = OllamaClient()

    prompt = f"Headline: {headline}\n\nBody excerpt: {body[:500]}"
    response = ollama.generate(
        model=os.getenv("EVENT_CLASSIFIER_MODEL", "llama3.2"),
        system=CLASSIFIER_SYSTEM_PROMPT,
        prompt=prompt,
    )
    parsed = ollama.parse_json(response)
    return parsed.get("event_type", "other"), float(parsed.get("confidence", 0.5))
```

---

## File: `python-agent/agents/sentiment_agent.py`

FinBERT runs locally via HuggingFace transformers. No API cost.
First load is slow (model download ~500MB); subsequent loads use cache.

```python
import os, logging
from transformers import pipeline

log = logging.getLogger(__name__)
FINBERT_MODEL = os.getenv("FINBERT_MODEL", "ProsusAI/finbert")

_pipeline = None


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        log.info(f"Loading FinBERT model: {FINBERT_MODEL}")
        _pipeline = pipeline(
            "text-classification",
            model=FINBERT_MODEL,
            return_all_scores=True,
        )
        log.info("FinBERT loaded.")
    return _pipeline


def score_sentiment(text: str) -> dict:
    """
    Returns { sentiment, confidence, scores, model }.
    FinBERT labels: positive | negative | neutral
    These map to: bullish | bearish | neutral in the signal output.
    """
    text = text[:1500]    # FinBERT max ~512 tokens; 1500 chars is safe
    pipe    = get_pipeline()
    results = pipe(text)[0]
    scores  = {r["label"]: r["score"] for r in results}

    dominant = max(scores, key=scores.get)
    label_map = {"positive": "bullish", "negative": "bearish", "neutral": "neutral"}

    return {
        "sentiment":  label_map.get(dominant, "neutral"),
        "confidence": scores[dominant],
        "scores":     scores,
        "model":      FINBERT_MODEL,
    }
```

---

## File: `python-agent/agents/impact_reasoner.py`

Mistral runs via Ollama (local). Chain-of-thought prompt produces structured JSON.
ALL output passes through governance/guardrails.py before the callback.

```python
import os, logging
from utils.ollama_client import OllamaClient

log = logging.getLogger(__name__)

IMPACT_SYSTEM_PROMPT = """
You are a financial markets analyst assistant. Your role is educational — helping
people understand how news events have historically affected markets.

You MUST follow these rules on every response:
- Never recommend buying or selling any security
- Never use the words: buy, sell, invest, purchase, short, guaranteed, price target,
  strong buy, strong sell, recommend, should buy, should sell
- Always express uncertainty — markets are unpredictable
- Always cite the specific news driving your analysis
- State what would change your assessment
- Output ONLY valid JSON matching the schema below — nothing else

OUTPUT SCHEMA:
{
  "event_type": "fed_rate|earnings|merger|regulatory|macro|other",
  "sentiment": "bullish|bearish|neutral",
  "confidence": 0.0-1.0,
  "affected_tickers": ["AAPL"],
  "affected_sectors": ["technology"],
  "time_horizon": "intraday|days|weeks|months",
  "impact_summary": "One paragraph explaining the likely market impact and historical context.",
  "historical_precedents": ["Brief reference to similar past events and their outcomes."],
  "uncertainty_factors": ["Specific factors that could make this analysis wrong."],
  "source_citations": ["Exact headline or source name that drove this analysis."],
  "disclaimer": "NOT FINANCIAL ADVICE. Educational analysis only."
}

If you cannot produce a confident analysis (confidence < 0.65), return ONLY:
{"signal": "no_signal", "reason": "Brief explanation of why analysis is not confident enough."}
"""


def analyze_impact(article: dict, sentiment: dict,
                   rag_context: list[str], ollama: OllamaClient) -> dict:
    """
    Produce a structured impact analysis for the given article.
    Returns raw JSON dict — caller must pass through validate_signal() in guardrails.py.
    """
    context_text = "\n---\n".join(rag_context[:3]) if rag_context else "No recent historical context available."

    prompt = f"""
Event type:    {article['event_type']}
Headline:      {article['headline']}
Sentiment:     {sentiment['sentiment']} (confidence: {sentiment['confidence']:.2f})
Tickers:       {article.get('tickers', [])}

Recent related news context (for historical comparison):
{context_text}

Analyze the likely market impact of this event for educational purposes.
Express genuine uncertainty. Do not recommend any action.
"""

    response = ollama.generate(
        model=os.getenv("IMPACT_REASONER_MODEL", "mistral"),
        system=IMPACT_SYSTEM_PROMPT,
        prompt=prompt,
    )

    return ollama.parse_json(response)
```

---

## File: `python-agent/utils/ollama_client.py`

```python
import os, json, logging, time
import httpx

log = logging.getLogger(__name__)
OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


class OllamaClient:
    def __init__(self, base_url: str = OLLAMA_BASE, timeout: int = 120):
        self.base_url = base_url
        self.timeout  = timeout

    def generate(self, model: str, system: str, prompt: str,
                 retries: int = 3) -> str:
        payload = {
            "model":   model,
            "system":  system,
            "prompt":  prompt,
            "stream":  False,
            "options": {"temperature": 0.1},
        }

        for attempt in range(retries):
            try:
                resp = httpx.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                return resp.json()["response"].strip()
            except httpx.ConnectError as e:
                if attempt == retries - 1:
                    raise RuntimeError(
                        f"Ollama unreachable at {self.base_url} after {retries} attempts"
                    ) from e
                wait = 2 ** attempt
                log.warning(f"Ollama connection error, retrying in {wait}s...")
                time.sleep(wait)

    def parse_json(self, text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text  = "\n".join(lines[1:-1])
        return json.loads(text)
```

---

## File: `python-agent/.env.example`

```bash
OLLAMA_BASE_URL=http://localhost:11434
EVENT_CLASSIFIER_MODEL=llama3.2
IMPACT_REASONER_MODEL=mistral
FINBERT_MODEL=ProsusAI/finbert
CHROMA_PATH=./chroma_db
DB_CONNECTION=postgresql://postgres:postgres@localhost/news_market
DOTNET_CALLBACK_URL=http://localhost:5000/api/signals/callback
PYTHON_AGENT_PORT=5001
SCHEDULE_TIME=07:00

# News provider — default is yfinance (free, no key needed)
# Set to "finnhub" and add FINNHUB_API_KEY to use Finnhub instead
NEWS_PROVIDER=yfinance
NEWS_DAYS_BACK=3

# Optional: only needed if NEWS_PROVIDER=finnhub
# FINNHUB_API_KEY=your_key_here
```

---

## Claude Code instructions for this layer

1. Build `governance/guardrails.py` (see `docs/GOVERNANCE.md`) BEFORE wiring up
   `impact_reasoner.py` outputs to the callback
2. Run `ollama pull llama3.2 && ollama pull mistral` before first run
3. FinBERT downloads on first call (~500MB); after that it's cached in `~/.cache/huggingface`
4. Phase 1 uses keyword-based `classify_event()` — upgrade to `classify_event_llm()` in Phase 2
5. `main.py` runs as a single-process consumer; run multiple instances for throughput
6. For production: add dead-letter queue in RabbitMQ for NACK'd messages
