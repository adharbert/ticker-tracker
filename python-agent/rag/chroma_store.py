import os, logging
import chromadb
from chromadb.utils import embedding_functions
from datetime import datetime, timedelta

log = logging.getLogger(__name__)
CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")
EMBED_MODEL = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")

_collection = None


def get_collection():
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
        log.info(f"ChromaDB ready at {CHROMA_PATH} "
                 f"({_collection.count()} documents)")
    return _collection


def add_article(article: dict) -> None:
    """
    Store an article in ChromaDB.
    Required keys: id, text, ticker, source, publish_date (YYYY-MM-DD),
                   event_type, source_tier
    """
    collection = get_collection()
    try:
        collection.add(
            documents=[article["text"]],
            ids=[str(article["id"])],
            metadatas=[{
                "ticker":       article.get("ticker", "MARKET"),
                "source":       article.get("source", "unknown"),
                "publish_date": article["publish_date"],
                "event_type":   article.get("event_type", "other"),
                "source_tier":  int(article.get("source_tier", 1)),
            }],
        )
    except Exception as e:
        if "already exists" in str(e).lower():
            log.debug(f"Article {article['id']} already in ChromaDB")
        else:
            raise


def query_recent(query_text: str,
                 ticker: str    = None,
                 days_back: int = 30,
                 n_results: int = 5,
                 min_tier: int  = 1) -> dict:
    """
    Temporal RAG query — always filters by date BEFORE semantic similarity.
    Never call ChromaDB without a date filter.
    """
    collection = get_collection()
    cutoff     = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    where: dict = {"publish_date": {"$gte": cutoff}}

    if ticker and min_tier > 1:
        where = {"$and": [where,
                          {"ticker":      {"$eq": ticker}},
                          {"source_tier": {"$gte": min_tier}}]}
    elif ticker:
        where = {"$and": [where, {"ticker": {"$eq": ticker}}]}
    elif min_tier > 1:
        where = {"$and": [where, {"source_tier": {"$gte": min_tier}}]}

    try:
        count = collection.count()
        if count == 0:
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

        return collection.query(
            query_texts=[query_text],
            where=where,
            n_results=min(n_results, count),
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        log.warning(f"ChromaDB query failed: {e}")
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


def get_stats() -> dict:
    return {"document_count": get_collection().count()}
