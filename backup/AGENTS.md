# AI Agents — Python Service Specification

> Claude Code: implement all files in `python-agent/` using this spec.
> Read `docs/ARCHITECTURE.md` first for the full pipeline context.

## Project setup

```bash
cd python-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### `requirements.txt`
```
pandas==2.2.2
openpyxl==3.1.2          # Excel reading
httpx==0.27.0             # async HTTP (Ollama + callback)
pika==1.3.2               # RabbitMQ
psycopg2-binary==2.9.9   # PostgreSQL
python-dotenv==1.0.1
```

## File: `python-agent/main.py`

Entry point — starts the RabbitMQ consumer loop.

```python
import os, json, logging
import pika
from dotenv import load_dotenv
from agents.schema_agent    import SchemaAgent
from agents.classify_agent  import ClassifyAgent
from agents.transform_agent import TransformAgent
from models.ollama_client   import OllamaClient

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
QUEUE_NAME   = os.getenv("RABBITMQ_QUEUE", "etl_jobs")


def process_job(ch, method, properties, body):
    """Called once per RabbitMQ message. Runs the full 3-agent pipeline."""
    try:
        msg = json.loads(body)
        job_id    = msg["jobId"]
        file_path = msg["filePath"]
        log.info(f"Processing job {job_id} — {file_path}")

        ollama = OllamaClient()

        # Step 1: Schema detection
        schema_agent  = SchemaAgent(ollama)
        schema        = schema_agent.run(job_id, file_path)

        # Step 2: Column classification
        classify_agent = ClassifyAgent(ollama)
        mapping        = classify_agent.run(job_id, schema)

        # Step 3: Transform & load
        transform_agent = TransformAgent(ollama)
        transform_agent.run(job_id, file_path, mapping)

        ch.basic_ack(delivery_tag=method.delivery_tag)
        log.info(f"Job {job_id} completed successfully.")

    except Exception as e:
        log.error(f"Job failed: {e}", exc_info=True)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def main():
    params = pika.URLParameters(RABBITMQ_URL)
    conn   = pika.BlockingConnection(params)
    ch     = conn.channel()

    ch.queue_declare(queue=QUEUE_NAME, durable=True)
    ch.basic_qos(prefetch_count=1)   # one job at a time per process
    ch.basic_consume(queue=QUEUE_NAME, on_message_callback=process_job)

    log.info(f"Waiting for jobs on queue '{QUEUE_NAME}' ...")
    ch.start_consuming()


if __name__ == "__main__":
    main()
```

## File: `python-agent/models/ollama_client.py`

Thin wrapper around the local Ollama REST API.

```python
import os, httpx, json, logging, time

log = logging.getLogger(__name__)

OLLAMA_BASE    = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_SCHEMA   = os.getenv("SCHEMA_MODEL",   "llama3.2")
DEFAULT_CLASSIFY = os.getenv("CLASSIFY_MODEL",  "mistral")
DEFAULT_TRANSFORM= os.getenv("TRANSFORM_MODEL", "phi3")


class OllamaClient:
    def __init__(self, base_url: str = OLLAMA_BASE, timeout: int = 120):
        self.base_url = base_url
        self.timeout  = timeout

    def generate(self, model: str, system: str, prompt: str,
                 retries: int = 3) -> str:
        """
        Call Ollama /api/generate. Returns the model's text response.
        Retries up to `retries` times on connection errors.
        """
        payload = {
            "model":  model,
            "system": system,
            "prompt": prompt,
            "stream": False,
            "options": { "temperature": 0.1 }   # low temp for structured output
        }

        for attempt in range(retries):
            try:
                resp = httpx.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=self.timeout
                )
                resp.raise_for_status()
                return resp.json()["response"].strip()
            except httpx.ConnectError as e:
                if attempt == retries - 1:
                    raise RuntimeError(
                        f"Ollama unreachable at {self.base_url} after {retries} attempts"
                    ) from e
                wait = 2 ** attempt
                log.warning(f"Ollama connection failed, retrying in {wait}s...")
                time.sleep(wait)

    def parse_json(self, text: str) -> dict:
        """Extract JSON from model response, stripping markdown fences if present."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text  = "\n".join(lines[1:-1])
        return json.loads(text)
```

## File: `python-agent/agents/schema_agent.py`

Detects column names and inferred data types from the uploaded file.

```python
import os, logging
import pandas as pd
import httpx

from models.ollama_client import OllamaClient, DEFAULT_SCHEMA

log = logging.getLogger(__name__)
CALLBACK_URL = os.getenv("DOTNET_CALLBACK_URL", "http://localhost:5000/api/etl/callback")

SYSTEM_PROMPT = """
You are a data schema analyst. Given a list of column names and sample values from a CSV or Excel file,
return a JSON object mapping each column name to its inferred data type.

Valid types: string, integer, float, boolean, date, datetime, email, phone, currency, id.

RULES:
- Return ONLY valid JSON. No explanation, no markdown fences.
- If unsure, use "string".
- Detect emails, phone numbers, and currency amounts specifically.

Example output:
{
  "CustomerID":   "id",
  "FirstName":    "string",
  "Email":        "email",
  "Balance":      "currency",
  "CreatedDate":  "date",
  "IsActive":     "boolean"
}
"""


class SchemaAgent:
    def __init__(self, ollama: OllamaClient, model: str = DEFAULT_SCHEMA):
        self.ollama = ollama
        self.model  = model

    def run(self, job_id: str, file_path: str) -> dict:
        """Analyze file schema and return { column_name: type } dict."""
        self._callback(job_id, "schema", "running")

        try:
            df     = self._load_file(file_path)
            prompt = self._build_prompt(df)

            log.info(f"[{job_id}] SchemaAgent calling {self.model}...")
            response = self.ollama.generate(self.model, SYSTEM_PROMPT, prompt)
            schema   = self.ollama.parse_json(response)

            log.info(f"[{job_id}] Schema detected: {schema}")
            self._callback(job_id, "schema", "done", payload={"schema": schema})
            return schema

        except Exception as e:
            self._callback(job_id, "schema", "failed", error=str(e))
            raise

    def _load_file(self, path: str) -> pd.DataFrame:
        ext = path.rsplit(".", 1)[-1].lower()
        if ext == "csv":
            return pd.read_csv(path, nrows=100)
        elif ext in ("xlsx", "xls"):
            return pd.read_excel(path, nrows=100)
        raise ValueError(f"Unsupported file type: {ext}")

    def _build_prompt(self, df: pd.DataFrame) -> str:
        sample = df.head(5).to_dict(orient="records")
        return (
            f"Columns: {list(df.columns)}\n\n"
            f"Pandas dtypes: {df.dtypes.to_dict()}\n\n"
            f"Sample rows (first 5):\n{sample}"
        )

    def _callback(self, job_id, step, status, payload=None, error=None):
        try:
            httpx.post(CALLBACK_URL, json={
                "jobId":   job_id,
                "step":    step,
                "status":  status,
                "payload": payload,
                "error":   error,
            }, timeout=10)
        except Exception as e:
            log.warning(f"Callback failed: {e}")
```

## File: `python-agent/agents/classify_agent.py`

Maps source columns to target database tables and columns.

```python
import os, logging
import httpx

from models.ollama_client import OllamaClient, DEFAULT_CLASSIFY

log = logging.getLogger(__name__)
CALLBACK_URL = os.getenv("DOTNET_CALLBACK_URL", "http://localhost:5000/api/etl/callback")

# ── Target table definitions ────────────────────────────────────────────────
# Expand this as you add more tables to your data model.
# Claude Code: move this to a config file or DB table for production.
TARGET_TABLES = {
    "customers": ["id", "first_name", "last_name", "email", "phone",
                  "created_at", "is_active"],
    "orders":    ["id", "customer_id", "order_date", "total_amount",
                  "status", "notes"],
    "products":  ["id", "name", "sku", "price", "stock_quantity", "category"],
    "employees": ["id", "first_name", "last_name", "email", "department",
                  "hire_date", "salary"],
}

SYSTEM_PROMPT = """
You are a database mapping expert. Given a source file's column schema and a list of
target database tables with their columns, return a JSON mapping of each source column
to its best-fit target table and column.

RULES:
- Return ONLY valid JSON. No explanation, no markdown fences.
- If a source column doesn't clearly map to any target, set table to "unknown".
- Prefer exact name matches, then semantic matches.
- One source column maps to exactly one target.

Example output:
{
  "CustomerID":  { "table": "customers", "column": "id" },
  "First Name":  { "table": "customers", "column": "first_name" },
  "Email Addr":  { "table": "customers", "column": "email" },
  "OrderTotal":  { "table": "orders",    "column": "total_amount" },
  "Notes":       { "table": "unknown",   "column": null }
}
"""


class ClassifyAgent:
    def __init__(self, ollama: OllamaClient, model: str = DEFAULT_CLASSIFY):
        self.ollama = ollama
        self.model  = model

    def run(self, job_id: str, schema: dict) -> dict:
        """Map source columns → target tables. Returns { source_col: {table, column} }."""
        self._callback(job_id, "classify", "running")

        try:
            prompt   = self._build_prompt(schema)
            log.info(f"[{job_id}] ClassifyAgent calling {self.model}...")
            response = self.ollama.generate(self.model, SYSTEM_PROMPT, prompt)
            mapping  = self.ollama.parse_json(response)

            log.info(f"[{job_id}] Mapping: {mapping}")
            self._callback(job_id, "classify", "done", payload={"mapping": mapping})
            return mapping

        except Exception as e:
            self._callback(job_id, "classify", "failed", error=str(e))
            raise

    def _build_prompt(self, schema: dict) -> str:
        tables_desc = "\n".join(
            f"  {table}: {cols}" for table, cols in TARGET_TABLES.items()
        )
        return (
            f"Source columns with types:\n{schema}\n\n"
            f"Target tables:\n{tables_desc}"
        )

    def _callback(self, job_id, step, status, payload=None, error=None):
        try:
            httpx.post(CALLBACK_URL, json={
                "jobId": job_id, "step": step, "status": status,
                "payload": payload, "error": error,
            }, timeout=10)
        except Exception as e:
            log.warning(f"Callback failed: {e}")
```

## File: `python-agent/agents/transform_agent.py`

Cleans, validates, and loads data into PostgreSQL.

```python
import os, logging
import pandas as pd
import psycopg2
import httpx

from models.ollama_client import OllamaClient, DEFAULT_TRANSFORM

log = logging.getLogger(__name__)
CALLBACK_URL = os.getenv("DOTNET_CALLBACK_URL", "http://localhost:5000/api/etl/callback")
DB_CONN      = os.getenv("DB_CONNECTION", "postgresql://postgres:postgres@localhost/etl_agent")


class TransformAgent:
    def __init__(self, ollama: OllamaClient, model: str = DEFAULT_TRANSFORM):
        self.ollama = ollama
        self.model  = model

    def run(self, job_id: str, file_path: str, mapping: dict):
        """Apply mapping, clean data, load to DB. Reports loaded/rejected counts."""
        self._callback(job_id, "transform", "running")

        try:
            df       = self._load_file(file_path)
            clean_df, rejections = self._apply_mapping(df, mapping)

            loaded   = self._load_to_db(job_id, clean_df, mapping)
            rejected = len(rejections)

            summary = (
                f"Loaded {loaded} rows. "
                f"Rejected {rejected} rows."
                + (f" Rejection reasons: {set(r['reason'] for r in rejections)}"
                   if rejections else "")
            )
            log.info(f"[{job_id}] {summary}")

            self._callback(job_id, "load", "done",
                           payload={"loaded": loaded, "rejected": rejected,
                                    "rejections": rejections[:10]},  # first 10 only
                           is_job_complete=True,
                           summary=summary)

        except Exception as e:
            self._callback(job_id, "transform", "failed", error=str(e))
            raise

    def _load_file(self, path: str) -> pd.DataFrame:
        ext = path.rsplit(".", 1)[-1].lower()
        return pd.read_csv(path) if ext == "csv" else pd.read_excel(path)

    def _apply_mapping(self, df: pd.DataFrame, mapping: dict):
        """Rename columns and validate. Returns (clean_df, rejections)."""
        rename = {}
        rejections = []

        for src_col, target in mapping.items():
            if target["table"] != "unknown" and src_col in df.columns:
                rename[src_col] = target["column"]

        # Drop unmapped columns
        mapped_cols = list(rename.keys())
        df = df[mapped_cols].rename(columns=rename)

        # Basic validation — flag nulls in required-looking ID columns
        clean_rows  = []
        for i, row in df.iterrows():
            if pd.isna(row).any():
                null_cols = row[pd.isna(row)].index.tolist()
                rejections.append({
                    "rowIndex": int(i),
                    "rawData":  row.to_dict(),
                    "reason":   f"Null values in {null_cols}"
                })
            else:
                clean_rows.append(row)

        clean_df = pd.DataFrame(clean_rows) if clean_rows else pd.DataFrame()
        return clean_df, rejections

    def _load_to_db(self, job_id: str, df: pd.DataFrame, mapping: dict) -> int:
        """Group rows by target table and INSERT. Returns total rows loaded."""
        if df.empty:
            return 0

        # Group columns by target table
        table_cols: dict[str, list[str]] = {}
        for src_col, target in mapping.items():
            if target["table"] != "unknown":
                table_cols.setdefault(target["table"], []).append(target["column"])

        total = 0
        conn  = psycopg2.connect(DB_CONN)

        try:
            with conn:
                with conn.cursor() as cur:
                    for table, cols in table_cols.items():
                        subset = df[[c for c in cols if c in df.columns]].copy()
                        if subset.empty:
                            continue
                        subset["etl_job_id"] = job_id

                        placeholders = ", ".join(["%s"] * len(subset.columns))
                        col_names    = ", ".join(subset.columns)
                        query        = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"

                        cur.executemany(query, subset.values.tolist())
                        total += len(subset)
        finally:
            conn.close()

        return total

    def _callback(self, job_id, step, status, payload=None, error=None,
                  is_job_complete=False, summary=None):
        try:
            httpx.post(CALLBACK_URL, json={
                "jobId":         job_id,
                "step":          step,
                "status":        status,
                "payload":       payload,
                "error":         error,
                "isJobComplete": is_job_complete,
                "summary":       summary,
            }, timeout=10)
        except Exception as e:
            log.warning(f"Callback failed: {e}")
```

## File: `python-agent/.env.example`

```bash
OLLAMA_BASE_URL=http://localhost:11434
SCHEMA_MODEL=llama3.2
CLASSIFY_MODEL=mistral
TRANSFORM_MODEL=phi3
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
RABBITMQ_QUEUE=etl_jobs
DB_CONNECTION=postgresql://postgres:postgres@localhost/etl_agent
DOTNET_CALLBACK_URL=http://localhost:5000/api/etl/callback
```

## Claude Code instructions for this layer

When implementing or extending the Python agent service:

1. Copy `.env.example` to `.env` and fill in your values
2. Run `ollama pull llama3.2 mistral phi3` before first run
3. The `TARGET_TABLES` dict in `classify_agent.py` should be moved to a JSON config
   file or loaded from a `target_schema` table in PostgreSQL for production
4. For fine-tuning: collect the agent's JSON outputs during production runs.
   Each `(prompt, good_output)` pair becomes a training example — see `docs/TRAINING.md`
5. Add retry logic and dead-letter queue handling in `main.py` for production
