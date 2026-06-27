# Frontend — React Specification

> Claude Code: use this to extend or debug the React app in `frontend/`.
> The core upload component is already built. This doc covers the full component map,
> state machine, and remaining work.

## What is already built

| File | Status | Description |
|------|--------|-------------|
| `src/components/FileUploader.jsx` | ✅ Done | Drag-drop upload, validation, job status panel |
| `src/api/etlApi.js`               | ✅ Done | `uploadFile()` and `getJobStatus()` |

## What still needs to be built

| File | Priority | Description |
|------|----------|-------------|
| `src/App.jsx`                      | High | Root with routing (React Router) |
| `src/components/JobHistory.jsx`    | High | List past upload jobs with status |
| `src/components/MappingPreview.jsx`| Medium | Show schema → table mapping before confirming load |
| `src/components/RejectionViewer.jsx`| Medium | View rejected rows and reasons |
| `src/hooks/useJobPolling.js`       | Medium | Extract polling logic from FileUploader |
| `src/pages/UploadPage.jsx`         | Low | Wrapper page for FileUploader |
| `src/pages/HistoryPage.jsx`        | Low | Wrapper page for JobHistory |

## Component map

```
App.jsx
├── /upload  → UploadPage
│   └── FileUploader          ✅ BUILT
│       ├── [drop zone]
│       ├── [file info strip]
│       └── JobStatusPanel
│           ├── [4 step rows]
│           └── [result summary]
└── /history → HistoryPage
    └── JobHistory             🔲 TODO
        └── JobRow (per job)
            └── RejectionViewer (expandable) 🔲 TODO
```

## State machine for upload flow

```
IDLE
  ↓ file selected (valid)
FILE_READY
  ↓ user clicks Upload
UPLOADING  (POST to /api/etl/upload)
  ↓ receives { jobId }
PROCESSING (polling every 2s)
  ↓ status == "completed"          ↓ status == "failed"
DONE                              FAILED
  ↓ user clicks Reset               ↓ user clicks Reset
IDLE                              IDLE
```

## API contract (what the backend returns)

```javascript
// GET /api/etl/status/:jobId
{
  jobId: "550e8400-e29b-41d4-a716-446655440000",
  status: "processing" | "completed" | "failed",
  agentSteps: {
    schema:    "pending" | "running" | "done" | "failed",
    classify:  "pending" | "running" | "done" | "failed",
    transform: "pending" | "running" | "done" | "failed",
    load:      "pending" | "running" | "done" | "failed"
  },
  summary: "Loaded 312 rows into customers table. 4 rows rejected."
}
```

## `src/hooks/useJobPolling.js` — spec

Extract polling from `FileUploader` into a reusable hook:

```javascript
// Usage:
// const { status, result, startPolling } = useJobPolling();

export function useJobPolling(intervalMs = 2000) {
  const [status,    setStatus]    = useState(null);
  const [result,    setResult]    = useState(null);
  const intervalRef               = useRef(null);

  function startPolling(jobId) {
    setStatus("processing");
    intervalRef.current = setInterval(async () => {
      const data = await getJobStatus(jobId);
      setResult(data);
      if (data.status === "completed" || data.status === "failed") {
        setStatus(data.status === "completed" ? "done" : "failed");
        clearInterval(intervalRef.current);
      }
    }, intervalMs);
  }

  useEffect(() => () => clearInterval(intervalRef.current), []);

  return { status, result, startPolling };
}
```

## `src/components/JobHistory.jsx` — spec

Fetches all past jobs and shows them in a list.

```javascript
// GET /api/etl/jobs — returns array of job summaries
// [{ jobId, fileName, status, createdAt, summary }]

// Renders:
// - Table or card list of past jobs
// - Status badge per job
// - "View details" button that expands RejectionViewer
// - Refresh button
```

## `src/components/MappingPreview.jsx` — spec

Shows the AI's column mapping before committing the load.
Only needed if you want a human-in-the-loop confirmation step.

```javascript
// Props: { mapping: { source_col: { table, column } }[], onConfirm, onCancel }
// Renders a 2-column table: Source column → Target table.column
// User can override any mapping via a select dropdown
// "Confirm & Load" button triggers the transform step
```

## Environment config

```bash
# frontend/.env
VITE_API_URL=http://localhost:5000
```

## Dev setup

```bash
cd frontend
npm create vite@latest . -- --template react
npm install
npm install react-router-dom    # if adding routing
npm run dev                     # http://localhost:5173
```

## Claude Code instructions for this layer

When extending the frontend:

1. Refactor `FileUploader.jsx` to use `useJobPolling` hook once it's extracted
2. Add React Router — wrap `FileUploader` in `UploadPage` and add `HistoryPage`
3. The `agentSteps` keys (`schema`, `classify`, `transform`, `load`) must match
   exactly what the backend returns — do not rename them
4. Keep polling interval at 2000ms — faster than that strains the API unnecessarily
5. When `status === "done"`, show a "Process another file" reset button
6. Style with plain inline styles (already established pattern) or add Tailwind —
   do not introduce a CSS-in-JS library
