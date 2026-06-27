# Architecture — ETL AI Agent System

> Reference for Claude Code. Read this before building any backend or agent code.

## System overview

```
Browser (React)
    │  multipart POST /api/etl/upload
    ▼
C# .NET 10 API
    │  1. Validates file (type, size)
    │  2. Saves raw file to blob/disk
    │  3. Creates job record in DB (status=queued)
    │  4. Publishes message to RabbitMQ
    │  returns { jobId }
    ▼
RabbitMQ queue: "etl_jobs"
    │  message: { jobId, filePath, originalName }
    ▼
Python AI Agent Service
    │  Consumes message
    │  Runs 3-agent pipeline (schema → classify → transform)
    │  POSTs step updates back to C# callback endpoint
    ▼
PostgreSQL
    │  Stores: job records, agent step status, loaded rows, audit log
    ▼
C# GET /api/etl/status/:jobId
    │  React polls every 2s
    ▼
Browser (React) — renders step-by-step progress
```

## Data flow in detail

### Upload flow (synchronous, < 500ms)

1. React `FileUploader` validates client-side (type + size)
2. POST to `C# /api/etl/upload` with `multipart/form-data`
3. `FileIngestionService` runs server-side validation again (never trust client)
4. File saved to configured blob path (`/uploads/{jobId}/{originalName}`)
5. `UploadJob` record inserted into `jobs` table with `status = "queued"`
6. Message published to RabbitMQ: `{ jobId, filePath, fileName }`
7. API returns `{ jobId }` immediately — does NOT wait for processing

### Agent flow (async, seconds to minutes)

```
Python consumer wakes on new RabbitMQ message
│
├─ Step 1: SchemaAgent
│   ├─ Load file with pandas (handles both CSV and Excel)
│   ├─ Extract: column names, sample 20 rows, infer pandas dtypes
│   ├─ Build prompt: "Given these columns and samples, return JSON of inferred types"
│   ├─ Call Ollama (llama3.2)
│   ├─ Parse response → { col_name: type }
│   ├─ POST callback: step=schema, status=done, payload={schema}
│   └─ Pass schema to ClassifyAgent
│
├─ Step 2: ClassifyAgent
│   ├─ Load target table definitions from config/DB
│   ├─ Build prompt: "Map these source columns to target tables/columns"
│   ├─ Call Ollama (mistral)
│   ├─ Parse response → { source_col: { table, column, transform? } }
│   ├─ POST callback: step=classify, status=done, payload={mapping}
│   └─ Pass mapping to TransformAgent
│
└─ Step 3: TransformAgent
    ├─ Apply column mapping
    ├─ Run type coercions and cleaning rules
    ├─ Validate each row; collect rejections with reasons
    ├─ Bulk INSERT clean rows into target tables
    ├─ INSERT rejected rows into audit_rejections table
    ├─ POST callback: step=load, status=done, payload={loaded, rejected, summary}
    └─ ACK RabbitMQ message
```

### Status polling flow

React polls `GET /api/etl/status/:jobId` every 2 seconds.
C# reads from `jobs` + `agent_steps` tables and returns the current snapshot.
When `status == "completed" | "failed"`, React stops polling.

## Database schema

```sql
-- Job tracking
CREATE TABLE jobs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status      TEXT NOT NULL DEFAULT 'queued',  -- queued|processing|completed|failed
    file_name   TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    summary     TEXT
);

-- Per-step agent status (one row per agent per job)
CREATE TABLE agent_steps (
    id       SERIAL PRIMARY KEY,
    job_id   UUID REFERENCES jobs(id),
    step     TEXT NOT NULL,   -- schema | classify | transform | load
    status   TEXT NOT NULL DEFAULT 'pending',  -- pending|running|done|failed
    payload  JSONB,           -- agent output for this step
    error    TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Rows rejected during transform
CREATE TABLE audit_rejections (
    id        SERIAL PRIMARY KEY,
    job_id    UUID REFERENCES jobs(id),
    row_index INT,
    raw_data  JSONB,
    reason    TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Message queue message format

Published by C#, consumed by Python:

```json
{
  "jobId":    "550e8400-e29b-41d4-a716-446655440000",
  "filePath": "/uploads/550e8400.../report.csv",
  "fileName": "report.csv",
  "fileType": "csv"
}
```

## Callback format (Python → C#)

Python POSTs to `DOTNET_CALLBACK_URL` after each agent step:

```json
{
  "jobId":   "550e8400-e29b-41d4-a716-446655440000",
  "step":    "schema",
  "status":  "done",
  "payload": { ... },
  "error":   null
}
```

Final step also sets top-level job status to `"completed"` or `"failed"`.

## Error handling strategy

| Failure point           | Behavior                                                        |
|-------------------------|-----------------------------------------------------------------|
| File validation fail    | 400 returned immediately, no job created                        |
| Queue publish fail      | 500 returned, job marked failed in DB                           |
| Agent step fails        | Step marked failed, job marked failed, RabbitMQ message NACKed |
| Ollama unreachable      | Retry 3x with backoff, then fail job                            |
| DB write fail           | Log to file, alert via callback, job stays in error state       |
| Transform partial fail  | Good rows still loaded; rejected rows go to audit_rejections    |

## Scalability notes

- Multiple Python agent instances can consume from the same RabbitMQ queue
- C# API is stateless — can run multiple instances behind a load balancer
- Job state lives in PostgreSQL, not in-process memory
- File storage should be a shared volume or object store if running multiple instances
