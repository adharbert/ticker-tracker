# News-to-Market Impact Agent

A personal learning project that ingests financial news, analyzes sentiment and market impact using local AI models, and generates structured signals with backtesting for educational purposes.

**This is NOT a trading system.** Every output layer enforces governance rules structurally in code. See [Governance](docs/GOVERNANCE.md).

---

## Overview

The system watches a configurable list of tickers, pulls news headlines and price data from Yahoo Finance (free, no API key), runs each article through a local AI pipeline, and surfaces sentiment signals in a React dashboard.

The AI pipeline runs entirely locally via Ollama — no cloud API costs. FinBERT handles financial sentiment; llama3.2 classifies event types; mistral generates chain-of-thought impact reasoning. All signals pass through a governance gate before reaching the database or UI.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + Vite + Recharts |
| API | .NET 10 / C# ASP.NET Core |
| Queue | RabbitMQ |
| AI Agents | Python 3.11 + Ollama (local) |
| Sentiment | FinBERT (`ProsusAI/finbert`, local) |
| Vector DB | ChromaDB (temporal RAG) |
| Relational DB | PostgreSQL |
| News & Prices | yfinance (free, no key) |

---

## Quick Start

```bash
# 1. Pull Ollama models
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

Copy `.env.example` to `.env` in both `backend/` and `python-agent/` before starting.

---

## Documentation

| Doc | Description |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) | Full system design, data flow diagram, and component responsibilities |
| [Phases](docs/PHASES.md) | Phased build sequence — Phase 1 through 4 with done-when checklists |
| [API](docs/API.md) | All C# .NET 10 endpoints, request/response shapes, and signal schema |
| [Agents](docs/AGENTS.md) | Python agent specs, prompts, pipeline wiring, and requirements |
| [RAG](docs/RAG.md) | ChromaDB setup and the temporal filtering pattern |
| [Frontend](docs/FRONTEND.md) | React component map, chart specs, and page layouts |
| [Training](docs/TRAINING.md) | FinBERT fine-tuning pipeline (Phase 3, requires 30+ labeled signals) |
| [Governance](docs/GOVERNANCE.md) | Hard rules, guardrails, and disclaimer enforcement |

---

## Default Watchlist

```
AAPL  MSFT  TSLA  SPY  QQQ
```

Covers large-cap tech, EV, and two broad-market ETFs — enough variety to see different event types (earnings, macro, sector news). Edit in `backend/appsettings.json` or directly in the database.

---

## Build Order

Follow the phases in [docs/PHASES.md](docs/PHASES.md) strictly:

- **Phase 1** — News + price ingestion, keyword event classification, ChromaDB RAG, basic UI
- **Phase 2** — FinBERT sentiment, mistral impact reasoning, governance gate, full dashboard
- **Phase 3** — Backtesting, FinBERT fine-tuning on labeled signals (requires 30+ from Phase 2)
- **Phase 4** — Daily digest email, Gmail integration, advanced scheduling

Do not start Phase 2 until Phase 1 runs end-to-end. Do not start Phase 3 until you have 30+ labeled signals.
