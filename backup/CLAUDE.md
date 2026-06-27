# ETL AI Agent — Claude Code Context

> This file is read automatically by Claude Code on startup.
> It gives you full project context so you can continue work without re-explanation.

## What this project is

A full-stack ETL pipeline that uses local AI agents (via Ollama — **no API cost**) to
ingest CSV / Excel files, detect schemas, classify columns, transform data, and route it
to the correct database table. Built for a small company that wants AI-powered data
ingestion without cloud AI spend.

## Tech stack

| Layer       | Technology                              | Why                                      |
|-------------|-----------------------------------------|------------------------------------------|
| Frontend    | React 18 + Vite                         | File upload UI, job status polling       |
| API         | .NET 10 / C# (ASP.NET Core Web API)     | Ingestion, queuing, status endpoints     |
| Queue       | RabbitMQ **or** Redis Streams           | Decouples upload from agent processing   |
| AI Agents   | Python 3.11 + Ollama                    | Free local LLMs, agentic ETL pipeline    |
| LLMs        | llama3.2, mistral, phi3 (via Ollama)    | All free, run locally, fine-tuneable     |
| Storage     | PostgreSQL (or SQL Server)              | Structured results                       |
| Blob store  | Local disk / Azure Blob / S3            | Raw file archive                         |

## Repository layout

```
etl-agent/
├── CLAUDE.md                  ← YOU ARE HERE (Claude Code reads this)
├── docs/
│   ├── ARCHITECTURE.md        ← Full system design, data flow diagrams
│   ├── AGENTS.md              ← AI agent specs, prompts, Ollama setup
│   ├── API.md                 ← All C# .NET 10 endpoints, models, queue setup
│   ├── FRONTEND.md            ← React component map, API contract, state machine
│   └── TRAINING.md            ← Fine-tuning guide: LoRA with Unsloth, dataset format
├── frontend/                  ← React + Vite app
│   └── src/
│       ├── components/
│       │   └── FileUploader.jsx    ✅ BUILT — drag-drop upload + job status UI
│       └── api/
│           └── etlApi.js           ✅ BUILT — uploadFile(), getJobStatus()
├── backend/                   ← .NET 10 C# API (NOT YET BUILT)
│   ├── Controllers/
│   │   └── EtlController.cs        🔲 TODO — POST /upload, GET /status/:id
│   ├── Services/
│   │   ├── FileIngestionService.cs 🔲 TODO — validate, store, enqueue
│   │   └── JobStatusService.cs     🔲 TODO — read job state from Redis/DB
│   ├── Models/
│   │   ├── UploadJob.cs            🔲 TODO — job record model
│   │   └── AgentStepStatus.cs      🔲 TODO — step tracking enum/model
│   └── Queue/
│       └── RabbitMqPublisher.cs    🔲 TODO — publish job to queue
└── python-agent/              ← Python AI service (NOT YET BUILT)
    ├── main.py                     🔲 TODO — queue consumer entry point
    ├── agents/
    │   ├── schema_agent.py         🔲 TODO — detect columns & data types
    │   ├── classify_agent.py       🔲 TODO — map cols → target DB tables
    │   └── transform_agent.py      🔲 TODO — clean, validate, load rows
    └── models/
        └── ollama_client.py        🔲 TODO — wrapper for local Ollama calls
```

## What is already built

### `frontend/src/components/FileUploader.jsx`
- Drag-and-drop or click-to-browse file picker
- Client-side validation: only `.csv`, `.xlsx`, `.xls`; max 50 MB
- Calls `uploadFile(file)` → receives `{ jobId }`
- Polls `getJobStatus(jobId)` every 2 seconds
- Renders a 4-step agent pipeline status panel: schema → classify → transform → load
- Shows per-step status: pending / running / done / failed

### `frontend/src/api/etlApi.js`
- `uploadFile(file)` — POST multipart to `VITE_API_URL/api/etl/upload`
- `getJobStatus(jobId)` — GET `VITE_API_URL/api/etl/status/:id`
- Base URL configured via `.env` `VITE_API_URL`

## API contract (what the backend must implement)

See `docs/API.md` for full details. Summary:

```
POST /api/etl/upload
  Body:    multipart/form-data  { file: <binary> }
  Returns: 200 { jobId: "uuid" }

GET  /api/etl/status/:jobId
  Returns: 200 {
    jobId:      "uuid",
    status:     "processing" | "completed" | "failed",
    agentSteps: {
      schema:    "pending" | "running" | "done" | "failed",
      classify:  "pending" | "running" | "done" | "failed",
      transform: "pending" | "running" | "done" | "failed",
      load:      "pending" | "running" | "done" | "failed"
    },
    summary: "Loaded 312 rows into customers. 4 rejected."
  }
```

## Agent pipeline (what Python must implement)

Three sequential agents, each powered by a local Ollama LLM:

```
[Queue message received]
        ↓
  SchemaAgent (llama3.2)
  - Reads file (pandas)
  - Sends column names + sample rows to LLM
  - LLM returns: { col_name: inferred_type }
        ↓
  ClassifyAgent (mistral)
  - Takes schema output
  - Sends schema + known target tables to LLM
  - LLM returns: { source_col: target_table.target_col }
        ↓
  TransformAgent (phi3)
  - Applies mapping, cleans data, validates types
  - Loads clean rows into PostgreSQL
  - Reports rejected rows with reasons
        ↓
  Posts status callback → C# API updates job record
```

## Key decisions made

1. **Ollama for all LLM calls** — zero API cost, runs on developer machine or a small
   GPU server. Models: llama3.2 (schema), mistral (classification), phi3 (transforms).

2. **Python for AI agents, C# for API** — Python has the best ML/pandas ecosystem.
   C# handles the REST API, file ingestion, and queue publishing. They communicate
   via a message queue (RabbitMQ) and a status callback HTTP call.

3. **Fine-tuning strategy** — start with prompt engineering only (system prompt +
   few-shot examples). Fine-tune with LoRA/Unsloth only after collecting 100+ real
   examples from production runs. See `docs/TRAINING.md`.

4. **No cloud AI required** — this entire system runs on-premises. Ollama pulls and
   caches models locally. The only external dependency is your database.

## How to continue building with Claude Code

Claude Code can build any of the TODO items above. Suggested order:

1. `docs/` — Read architecture docs before writing code for any layer
2. `backend/` — Build the C# .NET 10 API next (see `docs/API.md`)
3. `python-agent/` — Build the agent service (see `docs/AGENTS.md`)
4. Frontend polish — Add history page, column mapping preview, error detail view

To ask Claude Code to build a specific piece, say something like:
- "Build the EtlController.cs based on the API contract in CLAUDE.md"
- "Implement SchemaAgent in python-agent/agents/schema_agent.py"
- "Add a column mapping preview component to the frontend"

## Environment variables

```bash
# frontend/.env
VITE_API_URL=http://localhost:5000

# backend (appsettings.Development.json or env vars)
ConnectionStrings__Postgres=Host=localhost;Database=etl_agent;Username=postgres;Password=postgres
RabbitMq__Host=localhost
RabbitMq__Queue=etl_jobs
Redis__ConnectionString=localhost:6379
PythonAgent__CallbackUrl=http://localhost:5000/api/etl/callback

# python-agent/.env
OLLAMA_BASE_URL=http://localhost:11434
SCHEMA_MODEL=llama3.2
CLASSIFY_MODEL=mistral
TRANSFORM_MODEL=phi3
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
DB_CONNECTION=postgresql://postgres:postgres@localhost/etl_agent
DOTNET_CALLBACK_URL=http://localhost:5000/api/etl/callback
```

## Running locally (once built)

```bash
# 1. Start Ollama and pull models
ollama pull llama3.2
ollama pull mistral
ollama pull phi3

# 2. Start infrastructure
docker-compose up -d   # postgres + rabbitmq

# 3. Start .NET API
cd backend && dotnet run

# 4. Start Python agent
cd python-agent && pip install -r requirements.txt && python main.py

# 5. Start React dev server
cd frontend && npm install && npm run dev
```
