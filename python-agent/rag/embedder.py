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
    return get_model().encode(texts, show_progress_bar=False).tolist()
