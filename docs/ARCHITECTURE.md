# Architecture — News-to-Market Impact Agent

> Claude Code: read this before building any backend, agent, or frontend code.
> This document is the single source of truth for system design and data flow.

---

## System overview

```
                        ┌───────────────────────────────┐
                        │   React 18 + Vite Frontend    │
                        │  (SignalFeed, SentimentChart) │
                        └────────────┬──────────────────┘
                                     │  HTTP (REST + polling)
                        ┌────────────▼────────────────────┐
                        │   .NET 10 C# ASP.NET Core       │
                        │   (Signals, Watchlist, Ingest)  │
                        └──┬──────────────┬───────────────┘
                           │              │
              ┌────────────▼──┐   ┌───────▼────────────┐
              │  PostgreSQL   │   │     RabbitMQ       │
              │  (prices,     │   │  (news_analysis_   │
              │   signals,    │   │   jobs queue)      │
              │   watchlist)  │   └───────┬────────────┘
              └────────────▲──┘           │
                           │    ┌─────────▼───────────────────────────────┐
                           │    │   Python AI Agent Service               │
                           │    │                                         │
                           │    │  ┌─────────────────────────────────┐    │
                           │    │  │  1. EventClassifier (llama3.2)  │    │
                           │    │  │  2. SentimentAgent  (FinBERT)   │    │
                           │    │  │  3. ImpactReasoner  (mistral)   │    │
                           │    │  │  4. GovernanceGate  (guardrails)│    │
                           │    │  └─────────────────────────────────┘    │
                           │    │              │                          │
                           │    │  ┌───────────▼─────────────────────┐    │
                           │    │  │  ChromaDB (temporal RAG)        │    │
                           │    │  └─────────────────────────────────┘    │
                           │    └─────────────────────────────────────────┘
                           │                  │
                           └──────────────────┘
                         callback: POST /api/signals/callback

External sources (all free, no API key):
  yfinance news          →  Python news_fetcher.py  →  pipeline  →  callback  →  C#
  RSS feeds (8 feeds)    →  Python rss_fetcher.py   →  pipeline  →  callback  →  C#
  Google News RSS        →  Python rss_fetcher.py   →  pipeline  →  callback  →  C#
  SEC EDGAR (8-K, 10-Q)  →  Python rss_fetcher.py   →  pipeline  →  callback  →  C#
  yfinance OHLCV         →  Python price_fetcher.py →  PostgreSQL
  (Other providers can be added — see docs/AGENTS.md#news-provider-abstraction)
```

---

## Data flow in detail

### News ingestion flow

1. Python `main.py` runs a daily scheduler (APScheduler) at configured time
2. OR `POST /api/ingest/trigger` (C#) → calls `POST http://localhost:5001/trigger` (Python HTTP)
3. Python `news_fetcher.py` calls yfinance for each watchlist ticker — free, no key
4. Articles deduplicated and stored in PostgreSQL `news_articles` table
5. Each article runs through the full agent pipeline synchronously (classify → sentiment → impact → governance)
6. Governance-passed signals POSTed to C# callback at `DOTNET_CALLBACK_URL`
7. C# stores signal in DB; React sees it on next poll

**Provider abstraction:** `news_fetcher.py` uses a `NewsProvider` protocol.
yfinance is the default provider. To add Finnhub, Alpha Vantage, or any other
source later, implement the protocol and set `NEWS_PROVIDER=finnhub` in `.env`.

### Agent processing flow

```
Python _run() called per article (HTTP-triggered or scheduled — not RabbitMQ)
│
├─ Step 1: EventClassifier (keyword-based, Phase 1; upgradeable to llama3.2 in Phase 2)
│   ├─ Returns: event_type ∈ {fed_rate, earnings, merger, regulatory, macro, noise}
│   └─ If "noise" → log and skip article, done
│
├─ Step 2: SentimentAgent (FinBERT, local)
│   ├─ Loads ProsusAI/finbert via HuggingFace transformers
│   ├─ Returns: { sentiment: positive|negative|neutral, confidence: 0.0-1.0 }
│   └─ Understands domain terms: "rate hike", "beats estimates", "guidance cut"
│
├─ Step 3: RAG context retrieval
│   ├─ Query ChromaDB with temporal filter (last 30 days)
│   ├─ Filter: publish_date >= cutoff AND ticker = article.ticker
│   ├─ Returns top-5 semantically similar recent articles
│   └─ Used as context for impact reasoner
│
├─ Step 4: ImpactReasoner (mistral via Ollama)
│   ├─ Input: event_type + sentiment + rag_context + article
│   ├─ Chain-of-thought prompt produces structured JSON
│   └─ Returns: { event_type, sentiment, confidence, impact_summary, ... }
│
├─ Step 5: GovernanceGate (guardrails.py)
│   ├─ Confidence < 0.65 → discard
│   ├─ Prohibited phrases → discard
│   ├─ Low source credibility → flag
│   ├─ Single source → suppress alert
│   └─ Enforces disclaimer, governance_passed flag
│
├─ Step 6: Store + callback
│   ├─ Signal stored in PostgreSQL `signals` table
│   ├─ Article added to ChromaDB for future RAG queries
│   └─ POST to /api/signals/callback (C# updates DB, React sees it on next poll)
```

### Price fetch flow

```
price_fetcher.py (daily, before market open)
│
├─ Read watchlist tickers from PostgreSQL
├─ Call yfinance for 30-day OHLCV per ticker
└─ UPSERT into PostgreSQL prices table (ON CONFLICT DO UPDATE)
```

### React polling flow

```
React useSignals() hook
│
├─ SWR / setInterval polls GET /api/signals every 10s
├─ C# reads from signals + prices tables
└─ Returns paginated signal list with sentiment + governance metadata
```

---

## Database schema

```sql
-- Watchlist tickers
CREATE TABLE watchlist (
    ticker      TEXT PRIMARY KEY,
    name        TEXT,
    added_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Raw news articles (before agent processing)
CREATE TABLE news_articles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker          TEXT NOT NULL,
    headline        TEXT NOT NULL,
    body            TEXT,
    source_url      TEXT,
    source_name     TEXT,
    dedup_key       TEXT UNIQUE,              -- md5(ticker+headline+date), provider-agnostic
    published_at    TIMESTAMPTZ NOT NULL,
    ingested_at     TIMESTAMPTZ DEFAULT NOW(),
    processed       BOOLEAN DEFAULT FALSE
);

-- Generated signals (after full agent pipeline)
CREATE TABLE signals (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker                  TEXT NOT NULL,
    article_id              UUID REFERENCES news_articles(id),
    event_type              TEXT NOT NULL,    -- fed_rate|earnings|merger|regulatory|macro
    sentiment               TEXT NOT NULL,    -- bullish|bearish|neutral
    confidence              NUMERIC(4,3) NOT NULL,
    impact_summary          TEXT NOT NULL,
    time_horizon            TEXT NOT NULL,    -- intraday|days|weeks|months
    source_citations        TEXT[],
    uncertainty_factors     TEXT[],
    historical_precedents   TEXT[],
    disclaimer              TEXT NOT NULL,
    governance_passed       BOOLEAN NOT NULL DEFAULT TRUE,
    source_credibility_tier INTEGER NOT NULL DEFAULT 1,
    alert_suppressed        BOOLEAN DEFAULT FALSE,
    requires_human_review   BOOLEAN DEFAULT FALSE,
    governance_warnings     TEXT[],
    published_at            TIMESTAMPTZ NOT NULL,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- Daily OHLCV prices for backtesting and charts
CREATE TABLE prices (
    ticker      TEXT NOT NULL,
    date        DATE NOT NULL,
    open        NUMERIC(12,4),
    high        NUMERIC(12,4),
    low         NUMERIC(12,4),
    close       NUMERIC(12,4),
    volume      BIGINT,
    PRIMARY KEY (ticker, date)
);

-- Backtest results (Phase 3)
CREATE TABLE backtest_results (
    id              SERIAL PRIMARY KEY,
    ticker          TEXT NOT NULL,
    event_type      TEXT,
    look_ahead_days INTEGER NOT NULL,
    sample_size     INTEGER NOT NULL,
    accuracy        NUMERIC(5,4),             -- null if sample < 30
    accuracy_note   TEXT,
    baseline_accuracy NUMERIC(5,4) DEFAULT 0.50,
    vs_baseline     NUMERIC(5,4),
    disclaimer      TEXT NOT NULL,
    computed_at     TIMESTAMPTZ DEFAULT NOW()
);

-- FinBERT fine-tuning labels (Phase 3)
CREATE TABLE training_examples (
    id              SERIAL PRIMARY KEY,
    ticker          TEXT NOT NULL,
    headline        TEXT NOT NULL,
    body            TEXT,
    finbert_label   TEXT,                     -- positive|negative|neutral
    finbert_score   NUMERIC(5,4),
    human_label     TEXT,                     -- human correction if wrong
    is_correct      BOOLEAN,                  -- human-reviewed
    signal_id       UUID REFERENCES signals(id),
    reviewed_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Message queue formats

### C# → RabbitMQ (ingest job)

```json
{
  "articleId":   "uuid",
  "ticker":      "AAPL",
  "headline":    "Apple beats Q4 earnings estimates",
  "body":        "...",
  "sourceUrl":   "https://...",
  "sourceName":  "Reuters",
  "publishedAt": "2024-01-15T14:30:00Z"
}
```

### Python → C# callback (signal result)

```json
{
  "articleId":      "uuid",
  "ticker":         "AAPL",
  "signalId":       "uuid",
  "governancePassed": true,
  "rejectionReason": null,
  "signal": {
    "eventType":           "earnings",
    "sentiment":           "bullish",
    "confidence":          0.78,
    "impactSummary":       "...",
    "timeHorizon":         "days",
    "sourceCitations":     ["..."],
    "uncertaintyFactors":  ["..."],
    "disclaimer":          "NOT FINANCIAL ADVICE. Educational analysis only.",
    "sourceCredibilityTier": 3,
    "governanceWarnings":  []
  }
}
```

---

## Error handling strategy

| Failure point              | Behavior                                                         |
|----------------------------|------------------------------------------------------------------|
| yfinance fetch fails       | Log warning + skip that ticker for this cycle; retry next run    |
| RSS / Google News fails    | Log warning + skip that feed/ticker; rest of pipeline continues  |
| SEC EDGAR fetch fails      | Log warning + skip that ticker/form; rest of pipeline continues  |
| Ollama unreachable         | Retry 3× with exponential backoff, then raise RuntimeError       |
| Mistral returns bad JSON   | Multi-pass parse_json() cleanup; if all passes fail, per-article |
|                            | try/except in _run() skips that article and increments rejected  |
| FinBERT model not loaded   | Fail agent step, log error, article skipped                      |
| GovernanceGate rejects     | Signal discarded, rejection reason logged, article counted       |
| ChromaDB unavailable       | Skip RAG context, continue with empty context                    |
| Callback POST fails        | Log warning; signal NOT yet in .NET DB (Python does not write it)|

---

## Key architectural decisions

1. **FinBERT over general LLM** — pre-trained on 1.8M financial sentences. Understands
   domain language that general models miss. Runs locally, zero cost.

2. **Temporal RAG** — ChromaDB queries always include a date filter before semantic
   search. Without this, a 2019 article ranks equal to a 2024 article. Filter is
   enforced inside `query_recent()` — callers cannot bypass it.

3. **Two-model pipeline** — llama3.2 for fast event classification (cheap, local),
   mistral for deeper impact reasoning (slower, more capable). One model for both
   would be either too slow (mistral for all) or too shallow (llama3.2 for all).

4. **Governance in code, not docs** — `guardrails.py` is called by every agent before
   any output reaches the callback. It cannot be bypassed by config. See `docs/GOVERNANCE.md`.

5. **Backtest = evaluation, not prediction** — the backtester measures how well past
   signals correlated with actual price moves. It does not forecast future prices.
   This distinction is enforced in labels and UI copy throughout.

6. **Source credibility tiers** — Tier 3: wire services. Tier 2: major outlets.
   Tier 1: blogs/unknown. Single Tier-1 source → signal flagged. Single source of
   any tier → alert suppressed until corroborated.
