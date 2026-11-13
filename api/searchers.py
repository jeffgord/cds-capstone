"""Search backends. A backend turns a query into ranked chunk hits; the API does everything else
(dedupe by book, paging, snippets, cards). To plug in a new index, write a class with `search()` and
`info()` and return it from `load_searcher()`. See api/README.md."""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass
class ChunkHit:
    """One vector hit. Only gutenberg_id and score are required; the rest makes "Why this book" richer."""
    gutenberg_id: int
    score: float  # higher = closer
    doc_type: str | None = None  # "summary", "passage", or whatever the index calls its chunks
    passage_index: int | None = None  # index into the book's `passages` list, if the chunk is one
    text: str | None = None  # the embedded text, if the index stores it


class Searcher(Protocol):
    def search(self, query: str, n: int) -> list[ChunkHit]:
        """Up to n chunk hits, best first. Several hits per book are fine."""
        ...

    def info(self) -> dict:
        """Shown by /api/health: name, model, index_dir, n_vectors, score_kind."""
        ...


class LangChainFaissSearcher:
    """Any index saved with LangChain's FAISS.save_local, as long as each Document's metadata has
    `gutenberg_id`. Reads `doc_type` and `passage_index` when they're there (Estee's test_script.py
    writes both)."""

    def __init__(self, index_dir: Path, model_name: str, query_prefix: str = ""):
        from langchain_community.vectorstores import FAISS
        from langchain_community.vectorstores.utils import DistanceStrategy
        from langchain_huggingface import HuggingFaceEmbeddings

        self.index_dir = index_dir
        self.model_name = model_name
        self.query_prefix = query_prefix
        embeddings = HuggingFaceEmbeddings(model_name=model_name, encode_kwargs={"normalize_embeddings": True})
        # The index is a pickle: only load one you built yourself (it's gitignored, so it always is).
        self.store = FAISS.load_local(str(index_dir), embeddings, allow_dangerous_deserialization=True)
        # LangChain returns raw FAISS scores. Inner product is already a similarity; every other strategy
        # (EUCLIDEAN_DISTANCE, and COSINE, which LangChain also stores as IndexFlatL2) returns squared L2,
        # which on unit vectors is 2 - 2*cos, so cos = 1 - d/2.
        self.inner_product = self.store.distance_strategy == DistanceStrategy.MAX_INNER_PRODUCT

    def search(self, query: str, n: int) -> list[ChunkHit]:
        n = min(n, self.store.index.ntotal)
        hits = []
        for doc, raw in self.store.similarity_search_with_score(self.query_prefix + query, k=n):
            meta = doc.metadata
            passage_index = meta.get("passage_index")
            hits.append(ChunkHit(
                gutenberg_id=int(meta["gutenberg_id"]),
                score=float(raw) if self.inner_product else 1.0 - float(raw) / 2.0,
                doc_type=meta.get("doc_type"),
                passage_index=passage_index if isinstance(passage_index, int) and passage_index >= 0 else None,
                text=doc.page_content,
            ))
        return hits

    def info(self) -> dict:
        return {
            "searcher": "langchain-faiss",
            "model": self.model_name,
            "index_dir": str(self.index_dir),
            "n_vectors": self.store.index.ntotal,
            "score_kind": "cosine",
            "query_prefix": self.query_prefix or None,
        }


def load_searcher() -> Searcher:
    """Reads the env vars documented in api/README.md. Raises FileNotFoundError if there's no index."""
    index_dir = Path(os.getenv("SEARCH_INDEX_DIR", "gutenberg_faiss_test"))
    if not index_dir.is_absolute():
        index_dir = ROOT_DIR / index_dir
    if not (index_dir / "index.faiss").exists():
        raise FileNotFoundError(f"No index at {index_dir.name}/. Build it with: python test_script.py")
    return LangChainFaissSearcher(
        index_dir,
        model_name=os.getenv("SEARCH_MODEL", "BAAI/bge-base-en-v1.5"),
        query_prefix=os.getenv("SEARCH_QUERY_PREFIX", ""),
    )
