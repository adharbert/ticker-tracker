# Phases — Build Sequence

> Claude Code: always check which phase is current before building anything.
> Do not jump ahead. Each phase has a "done when" checklist.

---

## Phase 1 — Signal ingestion + RAG
**Goal:** News and prices flowing in, stored, queryable. No AI analysis yet.
**Time estimate:** 1–2 days

### What to build

**Python agent (`python-agent/`):**

```python
# agents/price_fetcher.py
# Fetches OHLCV data for watchlist tickers using yfinance
# Stores in PostgreSQL prices table
# Called daily before market open

import yfinance as yf
import psycopg2, os
from datetime import datetime, timedelta

def fetch_prices(tickers: list[str], days_back: int = 30):
    """Fetch daily OHLCV for each ticker and upsert into prices table."""
    conn = psycopg2.connect(os.getenv("DB_CONNECTION"))
    end   = datetime.today()
    start = end - timedelta(days=days_back)

    for ticker in tickers:
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
    conn.close()
```

```python
# agents/event_classifier.py
# Phase 1: simple keyword-based classifier
# Phase 2: upgrade to Ollama LLM classifier
# Returns one of: fed_rate | earnings | merger | regulatory | macro | other | noise

EVENT_KEYWORDS = {
    "fed_rate":   ["federal reserve", "fed", "rate hike", "rate cut", "fomc",
                   "interest rate", "powell", "basis points", "bps"],
    "earnings":   ["earnings", "eps", "revenue", "beats", "misses", "guidance",
                   "quarterly", "q1", "q2", "q3", "q4", "annual results"],
    "merger":     ["merger", "acquisition", "takeover", "buyout", "deal",
                   "acquired", "acquires", "merge"],
    "regulatory": ["sec", "ftc", "doj", "antitrust", "fine", "penalty",
                   "investigation", "subpoena", "regulation", "compliance"],
    "macro":      ["cpi", "inflation", "gdp", "unemployment", "jobs report",
                   "nonfarm", "pce", "treasury", "yield", "recession"],
}

def classify_event(headline: str, body: str = "") -> tuple[str, float]:
    """Returns (event_type, confidence_score)."""
    text   = (headline + " " + body).lower()
    scores = {}
    for event_type, keywords in EVENT_KEYWORDS.items():
        matches = sum(1 for kw in keywords if kw in text)
        if matches > 0:
            scores[event_type] = matches / len(keywords)

    if not scores:
        return "noise", 0.0

    best = max(scores, key=scores.get)
    # Noise threshold — don't emit signals for weak keyword matches
    if scores[best] < 0.05:
        return "noise", scores[best]
    return best, min(scores[best] * 10, 1.0)  # scale to 0-1
```

```python
# rag/chroma_store.py
# ChromaDB with mandatory temporal filtering
# NEVER query without a date filter — see docs/RAG.md

import chromadb
from chromadb.utils import embedding_functions
from datetime import datetime, timedelta
import os

CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")

def get_collection():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef     = embedding_functions.SentenceTransformerEmbeddingFunction(
                 model_name="all-MiniLM-L6-v2")
    return client.get_or_create_collection(
        name="financial_news",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"}
    )

def add_article(article: dict):
    """Store article chunk with required metadata."""
    collection = get_collection()
    collection.add(
        documents=[article["text"]],
        ids=[article["id"]],
        metadatas=[{
            "ticker":       article.get("ticker", "MARKET"),
            "source":       article["source"],
            "publish_date": article["publish_date"],  # ISO string "2024-01-15"
            "event_type":   article.get("event_type", "other"),
            "source_tier":  article.get("source_tier", 1),
        }]
    )

def query_recent(query_text: str, ticker: str = None,
                 days_back: int = 30, n_results: int = 5) -> list[dict]:
    """
    ALWAYS applies date filter before semantic search.
    This is the temporal RAG pattern — never skip the date filter.
    """
    collection = get_collection()
    cutoff = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    where = {"publish_date": {"$gte": cutoff}}
    if ticker:
        where = {"$and": [where, {"ticker": ticker}]}

    results = collection.query(
        query_texts=[query_text],
        where=where,
        n_results=n_results,
        include=["documents", "metadatas", "distances"]
    )
    return results
```

**C# backend (Phase 1 minimum):**
- `IngestController.cs` — POST `/api/ingest/trigger` for manual dev trigger
- `NewsIngestionService.cs` — calls Finnhub API, normalizes articles, queues them
- `WatchlistController.cs` — GET/POST/DELETE `/api/watchlist`
- `SignalsController.cs` — GET `/api/signals` (empty until Phase 2, returns `[]`)

**React frontend (Phase 1 minimum):**
- `WatchlistPage.jsx` — add/remove tickers, see current list
- `SignalFeed.jsx` — empty state with "Waiting for first ingest..." message
- App shell with navigation (Dashboard, Watchlist)

### Done when
- [x] `docker-compose up -d` starts without errors
- [x] yfinance returns news for watchlist tickers (13 articles stored on first run)
- [x] ChromaDB stores and retrieves articles with date filter
- [x] yfinance prices stored in PostgreSQL for all watchlist tickers (115 rows, 6 tickers)
- [x] Manual ingest trigger via `curl -X POST http://localhost:5261/api/ingest/trigger` works
- [x] React shows watchlist editor and empty signal feed

### Phase 1 implementation notes

**Deviations from original spec:**

- **PostgreSQL 18** — upgraded from postgres:16. Volume mount changed from
  `/var/lib/postgresql/data` → `/var/lib/postgresql` (required by postgres:18+, which
  manages its own versioned subdirectory). See docker-compose.yml.

- **Backend port is 5261**, not 5000. `frontend/.env` must set `VITE_API_URL=http://localhost:5261`.

- **`utils/db.py` INSERT fix** — `ingested_at` and `processed` columns are NOT NULL in
  the EF Core schema but were missing from the original INSERT statement. Fixed by
  adding `ingested_at = NOW()` and `processed = FALSE` explicitly.

- **yfinance multi-level DataFrame fix** — newer yfinance versions return multi-level
  column headers when downloading a single ticker. `price_fetcher.py` now flattens
  columns after `reset_index()` and uses `.iloc[0]` guards on OHLCV values.

- **yfinance upgrade required** — `yfinance==0.2.40` returns empty responses from
  Yahoo Finance. Upgrade with `pip install --upgrade yfinance` before first run.

- **RSS feeds added** — `agents/rss_fetcher.py` added as an additional news source
  alongside yfinance. Fetches Reuters, CNBC, MarketWatch, and Yahoo Finance RSS feeds.
  Matches articles to watchlist tickers via regex + company name lookup. Source tiers:
  Reuters = 3, CNBC/MarketWatch/Yahoo = 2. Requires `feedparser==6.0.11`.

- **`_process_article()` helper** — extracted from `fetch_and_store_all()` in
  `news_fetcher.py` to share identical dedup → classify → store logic between the
  yfinance loop and the RSS loop. Also fixes the original hardcoded `source_tier=1`.

---

## Phase 2 — Sentiment + impact analysis
**Goal:** Signals flowing from news → agents → DB → React UI with governance enforced.
**Time estimate:** 3–4 days
**Prerequisite:** Phase 1 done-checklist complete.

### What to build

**FinBERT sentiment agent:**

```python
# agents/sentiment_agent.py
from transformers import pipeline
import os

FINBERT_MODEL = os.getenv("FINBERT_MODEL", "ProsusAI/finbert")

# Load once at module level (slow first load, fast after)
_pipeline = None

def get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = pipeline("text-classification",
                             model=FINBERT_MODEL,
                             return_all_scores=True)
    return _pipeline

def score_sentiment(text: str) -> dict:
    """
    Returns { positive, negative, neutral } scores summing to 1.0.
    Uses the highest-scoring label as the signal.
    FinBERT understands financial domain language — use it, not a general model.
    """
    # FinBERT max input is 512 tokens — truncate if needed
    text = text[:1500]
    pipe    = get_pipeline()
    results = pipe(text)[0]
    scores  = {r["label"]: r["score"] for r in results}

    dominant = max(scores, key=scores.get)
    return {
        "sentiment":    dominant,               # positive | negative | neutral
        "confidence":   scores[dominant],
        "scores":       scores,                 # full distribution
        "model":        FINBERT_MODEL,
    }
```

**Impact reasoner (the core analysis):**

```python
# agents/impact_reasoner.py
# Reads: event_type + sentiment + retrieved RAG context
# Produces: structured impact analysis (mistral via Ollama)
# ALL output passes through governance/guardrails.py before callback

IMPACT_SYSTEM_PROMPT = """
You are a financial markets analyst assistant. Your role is educational — helping
people understand how news events have historically affected markets.

You MUST follow these rules on every response:
- Never recommend buying or selling any security
- Always express uncertainty — markets are unpredictable
- Always cite the specific news driving your analysis
- State what would change your assessment
- Output ONLY valid JSON matching the schema below

OUTPUT SCHEMA (return this JSON and nothing else):
{
  "event_type": "fed_rate|earnings|merger|regulatory|macro|other",
  "sentiment": "bullish|bearish|neutral",
  "confidence": 0.0-1.0,
  "affected_tickers": ["AAPL"],
  "affected_sectors": ["technology"],
  "time_horizon": "intraday|days|weeks|months",
  "impact_summary": "One paragraph explaining the likely impact and why.",
  "historical_precedents": ["Brief reference to similar past events."],
  "uncertainty_factors": ["What could make this analysis wrong."],
  "source_citations": ["Headline or source that drove this analysis."],
  "disclaimer": "NOT FINANCIAL ADVICE. Educational analysis only."
}

If confidence is below 0.65, return:
{"signal": "no_signal", "reason": "Insufficient confidence for analysis."}
"""

def analyze_impact(article: dict, sentiment: dict,
                   rag_context: list[str], ollama_client) -> dict:
    prompt = f"""
Event type: {article['event_type']}
Headline: {article['headline']}
Sentiment score: {sentiment['sentiment']} ({sentiment['confidence']:.2f})
Affected ticker(s): {article.get('tickers', [])}

Relevant historical context (from recent news):
{chr(10).join(rag_context[:3])}

Analyze the likely market impact of this event.
"""
    response = ollama_client.generate(
        model="mistral",
        system=IMPACT_SYSTEM_PROMPT,
        prompt=prompt
    )
    return ollama_client.parse_json(response)
```

**Governance gate (build this BEFORE wiring up impact_reasoner outputs):**
See `docs/GOVERNANCE.md` for the full `guardrails.py` spec. No signal reaches
the database or callback without passing through it.

**React components to build:**
- `SignalCard.jsx` — shows impact summary, confidence bar, disclaimer badge
- `SentimentChart.jsx` — Recharts line: sentiment score vs. closing price over time
- `GovernanceBadge.jsx` — red "NOT FINANCIAL ADVICE" pill, always visible
- `SignalFeed.jsx` — paginated, filterable by ticker + event type

### Done when
- [x] FinBERT scores sentiment for a news article locally (no API call)
- [x] mistral generates impact JSON via Ollama for an AAPL earnings story
- [x] Governance gate blocks a low-confidence signal (test with confidence=0.4)
- [x] Governance gate blocks a signal with "buy" in impact_summary
- [x] React SignalCard shows a real signal with disclaimer badge
- [x] SentimentChart renders with at least one ticker's data

### Implementation notes (deviations from spec)

- **FinBERT loaded offline** — model downloaded to `D:\models\finbert`; `FINBERT_MODEL`
  env var points to the local path. `TRANSFORMERS_OFFLINE=1` prevents HuggingFace
  network checks. Use `top_k=None` instead of deprecated `return_all_scores=True`.

- **Prohibited phrase "short" narrowed** — bare `"short"` triggered false positives on
  "short-term". Replaced with specific phrases: `"go short"`, `"short the"`,
  `"short position"`, `"short selling"`.

- **Signals table owned by .NET, not Python** — Python validates and sends the signal
  JSON to the `.NET callback endpoint. `ProcessCallbackAsync` in `SignalService.cs` is
  the sole DB writer. Python must not call `insert_signal()` directly.

- **ChromaDB date filter is numeric** — `query_recent()` filters on `publish_ts`
  (Unix int) using `$gte`, not the `publish_date` string. Both fields are stored on
  `add_article()` for human readability.

- **`GET /api/prices/{ticker}?days=30` added** — not in original spec; added to serve
  the `SentimentChart` component. Lives in `backend/Controllers/PricesController.cs`.

- **SentimentChart snaps signals to nearest price date** — `publishedAt` is set to
  `UtcNow` at callback time, which may be after the last price in the DB. The chart
  finds the nearest earlier price date so dots always render.

---

## Phase 3 — Prediction training + backtesting
**Goal:** Learn how to train a classifier and evaluate signal quality honestly.
**Time estimate:** 1 week
**Prerequisite:** 30+ labeled signals in `training_examples` DB table.

### What to build

See `docs/TRAINING.md` for full training pipeline.

Key sequence:
1. Run Phase 2 for several days to accumulate signals
2. Manually label `is_correct` in `training_examples` table (your human review)
3. Run `python-agent/scripts/backtest.py` — correlates signals with actual price moves
4. Run `python-agent/training/train_finbert.py` — LoRA fine-tune on your labels
5. Run `python-agent/training/evaluate_model.py` — compare fine-tuned vs baseline
6. If fine-tuned model outperforms on held-out test set, swap it in

Backtest governance (see `docs/GOVERNANCE.md#backtesting`):
- All backtest results pass through `BacktestGovernance.validate_result()`
- Look-ahead window hard-capped at 5 days
- Sample size < 30 → accuracy shown as null
- Baseline (coin flip = 50%) always shown alongside model accuracy

### Done when
- [ ] backtest.py correlates 30+ signals with actual 5-day price moves
- [x] Accuracy metric shown alongside 50% baseline in UI
- [ ] FinBERT fine-tuned on your labeled data
- [ ] Evaluation shows whether fine-tuned model outperforms base FinBERT
- [ ] BacktestPage renders results with all governance disclaimers

---

## Phase 4 — Multi-agent + full UI
**Goal:** Production-ready personal dashboard with scheduling, digest, and Gmail.
**Time estimate:** Ongoing
**Prerequisite:** Phase 3 done-checklist complete.

### What to build

- Gmail API integration — OAuth2 flow, keyword filter (earnings, Fed, tickers)
- `DailyIngestJob.cs` — .NET BackgroundService runs at 7am weekdays
- Daily digest email — HTML email template summarizing overnight signals
- Multi-agent orchestration — news agent + technicals agent run in parallel
- Advanced alert rules — configurable thresholds per ticker
- `DigestPage.jsx` — view past digests in UI

### Done when
- [ ] Daily ingest runs automatically at 7am without manual trigger
- [ ] Daily digest email arrives with overnight signals summarized
- [ ] Gmail alerts ingested alongside Finnhub news
- [ ] React dashboard auto-refreshes with new signals throughout the day
