# News-to-Market Impact Agent — Claude Code Context

> This file is read automatically by Claude Code on startup.
> It gives complete project context so work can continue without re-explanation.
> Companion project to `../etl-agent` — shares the same .NET 10 + React + Python stack.

---

## What this project is

A **personal learning project** that ingests financial news, analyzes sentiment and
market impact using local AI models, and generates structured signals with backtesting
for educational purposes.

**This is NOT a trading system.** Governance rules are enforced structurally in code,
not just in documentation. Every output layer enforces them — see `docs/GOVERNANCE.md`.

---

## Tech stack

| Layer        | Technology                          | Notes                                      |
|--------------|-------------------------------------|--------------------------------------------|
| Frontend     | React 18 + Vite + Recharts          | Sentiment charts, signal dashboard, digest |
| API          | .NET 10 / C# ASP.NET Core           | Ingest, schedule, status, signal endpoints |
| Queue        | RabbitMQ                            | Same instance as etl-agent project         |
| Agents       | Python 3.11 + Ollama                | Event classifier + impact reasoner (local) |
| Sentiment    | FinBERT (HuggingFace, local)        | `ProsusAI/finbert` — no API cost           |
| Vector DB    | ChromaDB                            | News RAG with temporal filtering           |
| Relational   | PostgreSQL                          | Prices, events, signals, backtest log      |
| Training     | HuggingFace PEFT + LoRA             | Fine-tune FinBERT on labeled signals       |
| Scheduler    | .NET BackgroundService + cron       | Daily ingestion at market open             |
| News source  | yfinance (free, no key)             | News headlines via Yahoo Finance — no cost |
| Price source | yfinance (free, no key)             | OHLCV data for backtesting                 |

---

## Repository layout

```
news-market-agent/
├── CLAUDE.md                        ← YOU ARE HERE
├── docker-compose.yml               ✅ DONE — postgres + rabbitmq + chromadb
├── init.sql                         ✅ DONE — all DB tables
├── .env.example                     ✅ DONE — all environment variables
│
├── docs/
│   ├── ARCHITECTURE.md              ✅ DONE — full system design + data flow
│   ├── PHASES.md                    ✅ DONE — build sequence, what's in each phase
│   ├── API.md                       ✅ DONE — all C# .NET 10 endpoints + models
│   ├── AGENTS.md                    ✅ DONE — all Python agent specs + prompts
│   ├── RAG.md                       ✅ DONE — ChromaDB setup + temporal query pattern
│   ├── FRONTEND.md                  ✅ DONE — React component map + chart specs
│   ├── TRAINING.md                  ✅ DONE — FinBERT fine-tuning pipeline
│   └── GOVERNANCE.md                ✅ DONE — all guardrails, rules, disclaimers
│
├── frontend/                        🔲 TODO — React + Vite app
│   └── src/
│       ├── pages/
│       │   ├── DashboardPage.jsx    🔲 TODO — signal feed + sentiment chart
│       │   ├── WatchlistPage.jsx    🔲 TODO — manage tickers
│       │   ├── DigestPage.jsx       🔲 TODO — daily digest view
│       │   └── BacktestPage.jsx     🔲 TODO — backtest results (Phase 3)
│       ├── components/
│       │   ├── SignalCard.jsx       🔲 TODO — single signal with confidence + disclaimer
│       │   ├── SentimentChart.jsx   🔲 TODO — Recharts: sentiment vs price over time
│       │   ├── SignalFeed.jsx       🔲 TODO — paginated list of signals
│       │   ├── WatchlistEditor.jsx  🔲 TODO — add/remove tickers
│       │   └── GovernanceBadge.jsx  🔲 TODO — "NOT FINANCIAL ADVICE" badge component
│       ├── hooks/
│       │   ├── useSignals.js        🔲 TODO — poll /api/signals with SWR
│       │   └── useWatchlist.js      🔲 TODO — CRUD watchlist
│       └── api/
│           └── marketApi.js         🔲 TODO — all API client calls
│
├── backend/                         🔲 TODO — .NET 10 C# API
│   ├── Controllers/
│   │   ├── SignalsController.cs     🔲 TODO — GET signals, GET digest
│   │   ├── WatchlistController.cs   🔲 TODO — CRUD watchlist
│   │   ├── IngestController.cs      🔲 TODO — trigger manual ingest
│   │   └── BacktestController.cs    🔲 TODO — Phase 3 backtest results
│   ├── Services/
│   │   ├── NewsIngestionService.cs  🔲 TODO — fetch + normalize + queue
│   │   ├── PriceService.cs          🔲 TODO — fetch OHLCV from yfinance via Python
│   │   ├── SignalService.cs         🔲 TODO — read/write signals from DB
│   │   └── DigestService.cs         🔲 TODO — assemble daily digest
│   ├── Models/
│   │   ├── Signal.cs                🔲 TODO — signal record + governance fields
│   │   ├── NewsArticle.cs           🔲 TODO — normalized article model
│   │   ├── WatchlistItem.cs         🔲 TODO — ticker + metadata
│   │   └── BacktestResult.cs        🔲 TODO — Phase 3
│   ├── Queue/
│   │   └── RabbitMqPublisher.cs     🔲 TODO — publish ingest jobs (reuse from etl-agent)
│   └── Scheduler/
│       └── DailyIngestJob.cs        🔲 TODO — BackgroundService triggered at 7am
│
└── python-agent/                    🔲 TODO — Python AI service
    ├── main.py                      🔲 TODO — scheduler + HTTP trigger + pipeline runner
    ├── requirements.txt             ✅ DONE — all dependencies listed in AGENTS.md
    ├── .env.example                 ✅ DONE
    ├── agents/
    │   ├── news_fetcher.py          🔲 TODO — yfinance news headlines fetch
    │   ├── event_classifier.py      🔲 TODO — classify news event type (Ollama)
    │   ├── sentiment_agent.py       🔲 TODO — FinBERT scoring
    │   ├── impact_reasoner.py       🔲 TODO — chain-of-thought impact analysis (mistral)
    │   └── price_fetcher.py         🔲 TODO — yfinance OHLCV fetch
    ├── rag/
    │   ├── chroma_store.py          🔲 TODO — ChromaDB setup + temporal query
    │   └── embedder.py              🔲 TODO — sentence-transformers embeddings
    ├── governance/
    │   └── guardrails.py            🔲 TODO — enforcement layer (all outputs pass through)
    ├── training/
    │   ├── collect_labels.py        🔲 TODO — Phase 3: export labeled signals
    │   ├── train_finbert.py         🔲 TODO — Phase 3: LoRA fine-tune
    │   └── evaluate_model.py        🔲 TODO — Phase 3: accuracy vs baseline
    └── scripts/
        └── backtest.py              🔲 TODO — Phase 3: correlate signals vs price moves
```

---

## Build order — follow phases strictly

**Phase 1 first.** Do not build Phase 2 until Phase 1 is running end-to-end.
Do not build Phase 3 until you have 30+ labeled signals from Phase 2.

```
Phase 1  → docs/PHASES.md#phase-1
  1. docker-compose up (postgres + rabbitmq + chromadb)
  2. python-agent/agents/price_fetcher.py
  3. python-agent/agents/news_fetcher.py       (yfinance news)
  4. python-agent/agents/event_classifier.py  (keyword-based)
  5. python-agent/rag/chroma_store.py
  6. backend/ IngestController (calls Python trigger endpoint)
  7. frontend/ WatchlistPage + SignalFeed (read-only)

Phase 2  → docs/PHASES.md#phase-2
  7. python-agent/agents/sentiment_agent.py  (FinBERT)
  8. python-agent/agents/impact_reasoner.py  (mistral + CoT prompt)
  9. python-agent/governance/guardrails.py   ← build this BEFORE impact_reasoner outputs
  10. frontend/ SignalCard + SentimentChart + GovernanceBadge

Phase 3  → docs/PHASES.md#phase-3
  11. python-agent/scripts/backtest.py
  12. python-agent/training/ (collect → train → evaluate)
  13. frontend/ BacktestPage

Phase 4  → docs/PHASES.md#phase-4
  14. Gmail integration, daily digest email, advanced scheduling
```

---

## What is already done (context files only — no runnable code yet)

All `docs/` files are complete specs. All `docker-compose.yml`, `init.sql`, and
`.env.example` are ready. No application code exists yet — Claude Code builds it.

---

## Watchlist (start small)

Default tickers for Phase 1. Edit in `backend/appsettings.json` or DB:

```json
["AAPL", "MSFT", "TSLA", "SPY", "QQQ"]
```

These cover large-cap tech, EV, and two broad-market ETFs — enough variety to see
different event types (earnings, macro, sector news). yfinance returns news for all
of these at no cost.

---

## API contract summary

Full specs in `docs/API.md`. React frontend depends on these shapes exactly.

```
GET  /api/signals?ticker=AAPL&limit=20&from=2024-01-01
GET  /api/signals/:id
GET  /api/digest/latest
GET  /api/watchlist
POST /api/watchlist  { ticker, name }
DEL  /api/watchlist/:ticker
POST /api/ingest/trigger            ← manual trigger (dev only)
GET  /api/backtest/:ticker          ← Phase 3
```

Every signal response includes mandatory governance fields:

```json
{
  "id": "uuid",
  "ticker": "AAPL",
  "eventType": "earnings",
  "sentiment": "bullish",
  "confidence": 0.78,
  "impactSummary": "...",
  "timeHorizon": "days",
  "sourceCitations": ["..."],
  "uncertaintyFactors": ["..."],
  "disclaimer": "NOT FINANCIAL ADVICE. Educational analysis only.",
  "publishedAt": "2024-01-15T09:30:00Z",
  "governancePassed": true,
  "sourceCredibilityTier": 3
}
```

---

## Governance — non-negotiable rules

Full spec in `docs/GOVERNANCE.md`. Summary of hard rules:

| Rule | Value | Effect of violation |
|------|-------|---------------------|
| Min confidence | 0.65 | Signal discarded entirely |
| Min source tier | 2 | Signal flagged, not shown |
| Min corroborating sources | 2 | Alert suppressed |
| Max backtest look-ahead | 5 days | Capped in code, not configurable |
| Min backtest sample | 30 events | Accuracy hidden, shown as null |
| Disclaimer | Always | Request rejected if missing |
| Prohibited phrases | buy/sell/invest/guaranteed | Signal rejected |
| No live trading hooks | Always | Architecture enforced |

---

## Environment variables

```bash
# backend appsettings.Development.json
ConnectionStrings__Postgres=Host=localhost;Database=news_market;Username=postgres;Password=postgres
RabbitMq__Host=localhost
RabbitMq__Queue=news_analysis_jobs
PythonAgent__BaseUrl=http://localhost:5001
PythonAgent__CallbackUrl=http://localhost:5000/api/signals/callback
Watchlist__DefaultTickers=AAPL,MSFT,TSLA,SPY,QQQ
Scheduler__DailyIngestTime=07:00

# python-agent .env
OLLAMA_BASE_URL=http://localhost:11434
EVENT_CLASSIFIER_MODEL=llama3.2
IMPACT_REASONER_MODEL=mistral
FINBERT_MODEL=ProsusAI/finbert
CHROMA_PATH=./chroma_db
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
DB_CONNECTION=postgresql://postgres:postgres@localhost/news_market
DOTNET_CALLBACK_URL=http://localhost:5000/api/signals/callback
PYTHON_AGENT_PORT=5001
NEWS_DAYS_BACK=3                     # how many days of news to fetch per run
SCHEDULE_TIME=07:00                  # daily ingest time (24h, local time)

# frontend .env
VITE_API_URL=http://localhost:5000
```

---

## Running the project

```bash
# 1. Pull required Ollama models (free, local)
ollama pull llama3.2
ollama pull mistral

# 2. Start infrastructure
docker-compose up -d

# 3. Start .NET API
cd backend && dotnet run

# 4. Start Python agent
cd python-agent && pip install -r requirements.txt && python main.py

# 5. Start React UI
cd frontend && npm install && npm run dev
# → http://localhost:5173

# 6. Trigger first ingest (dev)
curl -X POST http://localhost:5000/api/ingest/trigger
```

---

## Key architectural decisions

1. **FinBERT over general LLM for sentiment** — pre-trained on 1.8M financial sentences.
   Understands domain language (e.g., "rate hike" = negative for growth) that general
   models miss. Runs locally, zero cost. Fine-tune it in Phase 3 with your own labels.

2. **Temporal RAG** — ChromaDB queries always include a date filter applied *before*
   semantic search. Without this, a 2019 article ranks equal to a 2024 article.

3. **Two-model pipeline** — llama3.2 for fast event classification (cheap, local),
   mistral for deeper impact reasoning (slower, more capable). Don't use one model
   for both — classification needs speed; reasoning needs depth.

4. **Governance in code, not docs** — `guardrails.py` is called by every agent before
   any output reaches the callback. It cannot be bypassed. See `docs/GOVERNANCE.md`.

5. **Backtest = evaluation, not prediction** — the backtester correlates historical
   signals with actual price moves to measure signal quality. It does not forecast
   future prices. This distinction is enforced in labels and UI copy throughout.

6. **Source credibility tiers** — Tier 1: blogs/unknown. Tier 2: major outlets (CNBC,
   Bloomberg, WSJ). Tier 3: wire services (Reuters, AP). Signals from Tier 1 sources
   only are automatically flagged. Multi-source corroboration required for alerts.
