"""Builds book vectors for the graph experiments and caches them in graph/cache/.

From the search index (no re-embedding):
- index_summary:  each book's summary vector. It embeds "Classification: <LCC label>", so it leaks the
                  label and is only an upper bound.
- index_passages: the mean of the book's passage vectors. Their header carries Gutenberg bookshelves.

Re-embedded, leak-free ("text"): each book's own passages plus Gutenberg's description, with no title,
subjects or class. Saved per model as one vector per chunk plus which book it belongs to, so the
experiments can average them (one vector per book) or compare chunk to chunk.

Run: python graph/features.py   (~6 min on a laptop GPU for the four models; cached models are skipped)
"""
import json
import pickle
from pathlib import Path

import faiss
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
INDEX_DIR = ROOT / "gutenberg_faiss_test"
BOOKS_DIR = ROOT / "data" / "books"
CACHE = Path(__file__).resolve().parent / "cache"
MODELS = {  # short name -> Hugging Face model
    "bge-base": "BAAI/bge-base-en-v1.5",  # the search index's model
    "bge-small": "BAAI/bge-small-en-v1.5",
    "minilm": "sentence-transformers/all-MiniLM-L6-v2",
    "mpnet": "sentence-transformers/all-mpnet-base-v2",
}


def normalize(x: np.ndarray) -> np.ndarray:
    return x / np.linalg.norm(x, axis=1, keepdims=True).clip(1e-12)


def load_records() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(BOOKS_DIR.glob("*.json"))]


def book_texts(records: list[dict]) -> tuple[list[str], np.ndarray]:
    """Every chunk of a book's own words, and the row of the book each chunk belongs to."""
    texts, owner = [], []
    for i, r in enumerate(records):
        parts = [p.strip() for p in r.get("passages") or [] if p and p.strip()]
        if (r.get("description") or "").strip():
            parts.append(r["description"].strip())
        parts = parts or [r.get("title") or ""]  # title only when the book has no text at all
        texts += parts
        owner += [i] * len(parts)
    return texts, np.array(owner)


def mean_by_owner(chunks: np.ndarray, owner: np.ndarray, n: int) -> np.ndarray:
    out = np.zeros((n, chunks.shape[1]), dtype=np.float32)
    np.add.at(out, owner, chunks)
    return normalize(out)


def index_views(ids: list[int]) -> None:
    """Saves the summary and mean-passage vectors that are already in the search index."""
    index = faiss.read_index(str(INDEX_DIR / "index.faiss"))
    store, pos_to_id = pickle.load((INDEX_DIR / "index.pkl").open("rb"))
    vecs = index.reconstruct_n(0, index.ntotal)
    row = {g: i for i, g in enumerate(ids)}
    summary = np.zeros((len(ids), vecs.shape[1]), dtype=np.float32)
    passages, counts = np.zeros_like(summary), np.zeros(len(ids))
    for pos in range(index.ntotal):
        meta = store.search(pos_to_id[pos]).metadata
        i = row[int(meta["gutenberg_id"])]
        if meta["doc_type"] == "summary":
            summary[i] = vecs[pos]
        else:
            passages[i] += vecs[pos]
            counts[i] += 1
    passages[counts == 0] = summary[counts == 0]  # a few books have no usable passages
    np.save(CACHE / "index_summary.npy", normalize(summary))
    np.save(CACHE / "index_passages.npy", normalize(passages))


def embed(model_name: str, texts: list[str]) -> np.ndarray:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)
    return model.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=True)


def main() -> None:
    records = load_records()
    ids = [int(r["gutenberg_id"]) for r in records]
    CACHE.mkdir(exist_ok=True)
    (CACHE / "ids.json").write_text(json.dumps(ids))
    index_views(ids)
    texts, owner = book_texts(records)
    np.save(CACHE / "owner.npy", owner)
    (CACHE / "texts.json").write_text(json.dumps(texts))  # for the TF-IDF baseline
    for short, name in MODELS.items():
        path = CACHE / f"chunks_{short}.npy"
        if not path.exists():
            np.save(path, embed(name, texts).astype(np.float32))
        print(short, np.load(path).shape)


if __name__ == "__main__":
    main()
