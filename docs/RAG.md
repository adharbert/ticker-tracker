# RAG — ChromaDB Setup & Temporal Query Pattern

> Claude Code: implement `python-agent/rag/` using this spec.
> The temporal filter is the critical design decision — never query without it.

---

## Why temporal RAG matters

Standard RAG retrieves the most semantically similar documents regardless of when
they were published. For financial news, a 2019 article about "Apple earnings beat"
is semantically very similar to a 2024 article — but provides no useful context.

**Temporal RAG** enforces a date filter *before* semantic similarity ranking. Only
articles within the look-back window are candidates; similarity ranks within that set.

```
Without temporal filter:
  Query: "Apple Q3 earnings beat"
  → Returns: 2019 article (high similarity), 2021 article, 2024 article
                       ↑ useless for today's signal

With temporal filter (last 30 days):
  Query: "Apple Q3 earnings beat"
  → Returns: only articles from last 30 days, ranked by similarity
                       ↑ contextually relevant
```

---

## File: `python-agent/rag/embedder.py`

sentence-transformers handles embeddings. `all-MiniLM-L6-v2` is fast, free, and
good enough for news similarity. First load downloads ~90MB model.

```python
import os, logging
from sentence_transformers import SentenceTransformer

log = logging.getLogger(__name__)
EMBED_MODEL = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")

_model = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        log.info(f"Loading embedding model: {EMBED_MODEL}")
        _model = SentenceTransformer(EMBED_MODEL)
    return _model


def embed(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts. Returns list of float vectors."""
    model = get_model()
    return model.encode(texts, show_progress_bar=False).tolist()
```

---

## File: `python-agent/rag/chroma_store.py`

ChromaDB with persistent local storage. The `query_recent()` function is the
canonical temporal RAG pattern — always call it instead of raw ChromaDB queries.

```python
import os, logging
import chromadb
from chromadb.utils import embedding_functions
from datetime import datetime, timedelta

log = logging.getLogger(__name__)
CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")
EMBED_MODEL = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")

_collection = None


def get_collection():
    """Get or create the financial_news ChromaDB collection."""
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        ef     = embedding_functions.SentenceTransformerEmbeddingFunction(
                     model_name=EMBED_MODEL)
        _collection = client.get_or_create_collection(
            name="financial_news",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
        log.info(f"ChromaDB collection ready: {CHROMA_PATH}")
    return _collection


def add_article(article: dict):
    """
    Store a news article in ChromaDB.

    Required article fields:
        id           — unique string ID (use news_articles.id from PostgreSQL)
        text         — headline + body to embed
        ticker       — e.g. "AAPL"
        source       — e.g. "Reuters"
        publish_date — ISO date string "2024-01-15"
        event_type   — classified event type
        source_tier  — int 1|2|3
    """
    collection = get_collection()

    # Skip if already stored (ChromaDB raises on duplicate IDs)
    try:
        collection.add(
            documents=[article["text"]],
            ids=[str(article["id"])],
            metadatas=[{
                "ticker":       article.get("ticker", "MARKET"),
                "source":       article.get("source", "unknown"),
                "publish_date": article["publish_date"],   # "YYYY-MM-DD"
                "event_type":   article.get("event_type", "other"),
                "source_tier":  int(article.get("source_tier", 1)),
            }],
        )
    except Exception as e:
        if "already exists" in str(e).lower():
            log.debug(f"Article {article['id']} already in ChromaDB — skipping")
        else:
            raise


def query_recent(query_text: str,
                 ticker: str     = None,
                 days_back: int  = 30,
                 n_results: int  = 5,
                 min_tier: int   = 1) -> dict:
    """
    ALWAYS apply date filter before semantic search.
    This is the temporal RAG pattern — never query ChromaDB without a date filter.

    Args:
        query_text  — the text to find similar articles for
        ticker      — optional ticker filter (e.g. "AAPL")
        days_back   — look-back window in days (default 30)
        n_results   — max number of results to return
        min_tier    — minimum source credibility tier (1 = all)

    Returns:
        ChromaDB query result dict with "documents", "metadatas", "distances"
    """
    collection = get_collection()
    cutoff     = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    # Build where clause — date filter is always required
    where: dict = {"publish_date": {"$gte": cutoff}}

    if ticker and min_tier > 1:
        where = {"$and": [
            where,
            {"ticker":      {"$eq": ticker}},
            {"source_tier": {"$gte": min_tier}},
        ]}
    elif ticker:
        where = {"$and": [where, {"ticker": {"$eq": ticker}}]}
    elif min_tier > 1:
        where = {"$and": [where, {"source_tier": {"$gte": min_tier}}]}

    try:
        return collection.query(
            query_texts=[query_text],
            where=where,
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        log.warning(f"ChromaDB query failed: {e}")
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


def get_collection_stats() -> dict:
    """Return basic stats about what's stored in ChromaDB."""
    collection = get_collection()
    count      = collection.count()
    return {"document_count": count, "collection": "financial_news"}
```

---

## Metadata schema

Every document stored in ChromaDB must have these metadata fields:

| Field          | Type   | Values / Notes                                            |
|----------------|--------|-----------------------------------------------------------|
| `ticker`       | string | "AAPL", "MSFT", etc. Use "MARKET" for macro news          |
| `source`       | string | Source name, e.g. "Reuters", "CNBC"                      |
| `publish_date` | string | ISO date "YYYY-MM-DD" — used for temporal filtering       |
| `event_type`   | string | fed_rate \| earnings \| merger \| regulatory \| macro \| other |
| `source_tier`  | int    | 1 (blogs) \| 2 (major outlets) \| 3 (wire services)      |

The `publish_date` must be a string in "YYYY-MM-DD" format. ChromaDB's `$gte`
operator does lexicographic comparison, which works correctly for ISO dates.

---

## Temporal filter patterns

```python
# Last 30 days for a specific ticker (standard use case)
query_recent("Apple earnings beat", ticker="AAPL", days_back=30)

# Last 7 days for any ticker — broad macro context
query_recent("Federal Reserve rate decision", days_back=7)

# Last 90 days, only high-credibility sources
query_recent("merger acquisition", ticker="MSFT", days_back=90, min_tier=2)

# WRONG — never do this (no date filter)
# collection.query(query_texts=["earnings"], n_results=5)
```

---

## ChromaDB storage location

```bash
# Default: ./chroma_db relative to where main.py runs
CHROMA_PATH=./chroma_db

# In Docker: mount as a volume so data survives container restarts
# docker-compose.yml:
#   volumes:
#     - chroma_data:/app/chroma_db
```

---

## Integration with impact_reasoner.py

```python
# In main.py, before calling analyze_impact():
from rag.chroma_store import query_recent

rag_results  = query_recent(headline, ticker=ticker, days_back=30, n_results=5)
rag_context  = rag_results.get("documents", [[]])[0]  # flat list of text strings

# rag_context is passed to analyze_impact() as the historical context
raw_signal = analyze_impact(article_ctx, sentiment, rag_context, ollama)
```

---

## ChromaDB in docker-compose

```yaml
# Add to docker-compose.yml
chromadb:
  image: chromadb/chroma:latest
  ports:
    - "8000:8000"
  volumes:
    - chroma_data:/chroma/chroma
  environment:
    - IS_PERSISTENT=TRUE

volumes:
  chroma_data:
```

If using ChromaDB as a server (not local PersistentClient), change the client
initialization in `get_collection()`:

```python
client = chromadb.HttpClient(host="localhost", port=8000)
```

The default setup uses `PersistentClient` (local file storage), which is simpler
for development. Either approach works; choose based on your deployment model.

---

## Claude Code instructions for this layer

1. The `publish_date` field must be populated on every `add_article()` call — it is
   the critical field that makes temporal filtering work
2. Test temporal filtering explicitly: add an old article and verify it does not appear
   in results for `days_back=7`
3. The `get_collection()` singleton pattern is intentional — ChromaDB connections are
   expensive; create once and reuse
4. ChromaDB will automatically create the `./chroma_db` directory if it doesn't exist
5. Embedding model downloads on first use (~90MB); subsequent runs use local cache
