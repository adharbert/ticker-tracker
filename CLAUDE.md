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
| Queue        | RabbitMQ 4                          | Same instance as etl-agent project; docker-compose uses rabbitmq:4-management |
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
├── frontend/                        ✅ DONE (Phase 1 + 2)
│   └── src/
│       ├── pages/
│       │   ├── DashboardPage.jsx    ✅ DONE — signal feed + sentiment chart + ingest trigger
│       │   ├── WatchlistPage.jsx    ✅ DONE — manage tickers
│       │   ├── DigestPage.jsx       🔲 TODO — Phase 4
│       │   └── BacktestPage.jsx     🔲 TODO — Phase 3
│       ├── components/
│       │   ├── SignalCard.jsx       ✅ DONE — confidence bar, governance badge, warnings
│       │   ├── SentimentChart.jsx   ✅ DONE — Recharts: sentiment vs price over time
│       │   ├── SignalFeed.jsx       ✅ DONE — ticker + event type filter, SWR polling
│       │   ├── WatchlistEditor.jsx  ✅ DONE — add/remove tickers
│       │   └── GovernanceBadge.jsx  ✅ DONE — compact + full variants
│       ├── hooks/
│       │   ├── useSignals.js        ✅ DONE — SWR polling every 60s
│       │   └── useWatchlist.js      ✅ DONE — CRUD watchlist
│       └── api/
│           └── marketApi.js         ✅ DONE — signals, watchlist, prices, ingest trigger
│
├── backend/                         ✅ DONE (Phase 1 + 2)
│   ├── Controllers/
│   │   ├── SignalsController.cs     ✅ DONE — GET signals, POST callback
│   │   ├── WatchlistController.cs   ✅ DONE — CRUD watchlist
│   │   ├── IngestController.cs      ✅ DONE — trigger manual ingest
│   │   ├── PricesController.cs      ✅ DONE — GET prices per ticker (added Phase 2)
│   │   └── BacktestController.cs    🔲 TODO — Phase 3
│   ├── Services/
│   │   ├── NewsIngestionService.cs  ✅ DONE — calls Python agent trigger
│   │   ├── SignalService.cs         ✅ DONE — read signals + process callback
│   │   └── DigestService.cs         🔲 TODO — Phase 4
│   ├── Models/
│   │   ├── Signal.cs                ✅ DONE
│   │   ├── NewsArticle.cs           ✅ DONE
│   │   ├── WatchlistItem.cs         ✅ DONE
│   │   └── BacktestResult.cs        🔲 TODO — Phase 3
│   └── Scheduler/
│       └── DailyIngestJob.cs        ✅ DONE — BackgroundService at configurable time
│
└── python-agent/                    ✅ DONE (Phase 1 + 2)
    ├── main.py                      ✅ DONE — scheduler + HTTP trigger + pipeline runner
    ├── requirements.txt             ✅ DONE
    ├── .env.example                 ✅ DONE
    ├── agents/
    │   ├── news_fetcher.py          ✅ DONE — yfinance + RSS feeds, Phase 2 AI pipeline
    │   ├── rss_fetcher.py           ✅ DONE — Reuters/CNBC/MarketWatch/Yahoo RSS
    │   ├── event_classifier.py      ✅ DONE — keyword-based classifier
    │   ├── sentiment_agent.py       ✅ DONE — FinBERT scoring (local)
    │   ├── impact_reasoner.py       ✅ DONE — mistral CoT impact analysis
    │   └── price_fetcher.py         ✅ DONE — yfinance OHLCV fetch
    ├── rag/
    │   ├── chroma_store.py          ✅ DONE — ChromaDB with numeric timestamp filter
    │   └── embedder.py              ✅ DONE
    ├── governance/
    │   └── guardrails.py            ✅ DONE — validates every signal before callback
    ├── training/
    │   ├── collect_labels.py        🔲 TODO — Phase 3
    │   ├── train_finbert.py         🔲 TODO — Phase 3
    │   └── evaluate_model.py        🔲 TODO — Phase 3
    └── scripts/
        └── backtest.py              🔲 TODO — Phase 3
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

**Phase 1 and Phase 2 are fully implemented and verified end-to-end.**

- All `docs/` specs, `docker-compose.yml`, `init.sql`, `.env.example` complete
- Full Python pipeline: news fetch → event classify → FinBERT sentiment → mistral impact → governance gate → .NET callback
- Full .NET backend: watchlist CRUD, signal storage, ingest trigger, prices endpoint
- Full React frontend: signal feed, watchlist editor, sentiment/price chart, governance badge
- Daily scheduler running Mon–Fri at 07:00 (local time) in `python-agent/main.py`

**Accumulating signals for Phase 3** — need 30+ governance-passed signals before backtesting.

---

## Watchlist

Managed via the UI (WatchlistPage) or directly in the DB. Current tickers as of Phase 2:

```json
["AAPL", "MSFT", "TSLA", "SPY", "QQQ", "NVDA", "BTC-USD"]
```

BTC-USD is supported — the RSS fetcher maps "bitcoin"/"btc"/"crypto" keywords to the
BTC-USD ticker via `_COMPANY_NAME_MAP` in `python-agent/agents/rss_fetcher.py`.

---

## API contract summary

Full specs in `docs/API.md`. React frontend depends on these shapes exactly.

```
GET  /api/signals?ticker=AAPL&limit=20
GET  /api/signals/:id
GET  /api/watchlist
POST /api/watchlist  { ticker, name }
DEL  /api/watchlist/:ticker
POST /api/ingest/trigger            ← manual trigger (dev only)
GET  /api/prices/:ticker?days=30    ← added Phase 2 (serves SentimentChart)
GET  /api/digest/latest             ← Phase 4
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
| Prohibited phrases | buy/sell/invest/guaranteed/go short/short the/short position/short selling | Signal rejected |
| No live trading hooks | Always | Architecture enforced |

---

## Environment variables

```bash
# backend appsettings.Development.json
# NOTE: .NET API runs on port 5261 (auto-assigned by dotnet new — check launchSettings.json)
ConnectionStrings__Postgres=Host=localhost;Port=5433;Database=news_market;Username=postgres;Password=postgres
RabbitMq__Host=localhost
RabbitMq__Queue=news_analysis_jobs
PythonAgent__BaseUrl=http://localhost:5001
Watchlist__DefaultTickers=AAPL,MSFT,TSLA,SPY,QQQ
Scheduler__DailyIngestTime=07:00

# python-agent .env
OLLAMA_BASE_URL=http://localhost:11434
EVENT_CLASSIFIER_MODEL=llama3.2
IMPACT_REASONER_MODEL=mistral
FINBERT_MODEL=D:\models\finbert      # local path — model downloaded offline
TRANSFORMERS_OFFLINE=1               # prevents HuggingFace network checks
CHROMA_PATH=./chroma_db
DB_CONNECTION=postgresql://postgres:postgres@localhost:5433/news_market
DOTNET_CALLBACK_URL=http://localhost:5261/api/signals/callback
PYTHON_AGENT_PORT=5001
NEWS_DAYS_BACK=3                     # how many days of news to fetch per run
SCHEDULE_TIME=07:00                  # daily ingest time (24h, local time)

# frontend .env
VITE_API_URL=http://localhost:5261
```

---

## Running the project

```bash
# 1. Pull required Ollama models (free, local) — one-time setup
ollama pull llama3.2
ollama pull mistral

# 2. Start infrastructure
docker-compose up -d

# 3. Start .NET API  (runs on port 5261)
cd backend && dotnet run

# 4. Start Python agent  (runs on port 5001, scheduler starts automatically)
cd python-agent && python main.py

# 5. Start React UI
cd frontend && npm run dev
# → http://localhost:5173

# 6. Trigger manual ingest (dev / first run)
curl -X POST http://localhost:5261/api/ingest/trigger
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

7. **.NET owns the signals table** — Python runs the full AI pipeline but does NOT
   write to the `signals` table. Python calls the .NET callback endpoint; `ProcessCallbackAsync`
   in `SignalService.cs` is the sole writer. This keeps the governance audit trail in
   one place and prevents double-writes.

8. **ChromaDB date filter uses numeric timestamps** — ChromaDB 0.5+ requires numeric
   values for `$gte`/`$lte` operators. Articles are stored with both `publish_date`
   (string, human-readable) and `publish_ts` (Unix int, used for filtering).

9. **Signal dots snapped to nearest price date** — signals have `publishedAt = UtcNow`
   (time of callback), which may be after the latest price in the DB. The `SentimentChart`
   snaps each signal to the nearest earlier price date so dots always appear on the chart.
