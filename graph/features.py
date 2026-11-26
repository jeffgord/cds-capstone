"""Builds one vector per book, three ways, and caches them in graph/cache/.

- summary:  the book's summary vector from the search index. It embeds "Classification: <LCC label>",
            so LCC results on it are an upper bound, not a fair test.
- passages: the mean of the book's passage vectors from the index. Their header carries the bookshelves.
- text:     the book's own text (passages + Gutenberg's description) re-embedded with no metadata at all.
            This is the leak-free view.

Run: python graph/features.py   (~2 min on a laptop GPU, mostly the "text" view)
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
MODEL = "BAAI/bge-base-en-v1.5"  # same model as the search index


def normalize(x: np.ndarray) -> np.ndarray:
    return x / np.linalg.norm(x, axis=1, keepdims=True).clip(1e-12)


def index_views(ids: list[int]) -> dict[str, np.ndarray]:
    """Reads the vectors already in the search index and groups them by book."""
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
    # A book with no passages falls back to its summary vector (rare: a few books have no usable text).
    passages[counts == 0] = summary[counts == 0]
    return {"summary": normalize(summary), "passages": normalize(passages)}


def text_view(records: list[dict]) -> np.ndarray:
    """Embeds each book's own words with no title, subjects or class, and averages per book."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL)
    texts, owner = [], []
    for i, r in enumerate(records):
        parts = [p.strip() for p in r.get("passages") or [] if p and p.strip()]
        if (r.get("description") or "").strip():
            parts.append(r["description"].strip())
        texts += parts or [r.get("title") or ""]  # title only when the book has no text at all
        owner += [i] * max(len(parts), 1)
    vecs = model.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=True)
    out = np.zeros((len(records), vecs.shape[1]), dtype=np.float32)
    np.add.at(out, np.array(owner), vecs)
    return normalize(out)


def main() -> None:
    records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(BOOKS_DIR.glob("*.json"))]
    ids = [int(r["gutenberg_id"]) for r in records]
    CACHE.mkdir(exist_ok=True)
    views = index_views(ids) | {"text": text_view(records)}
    for name, x in views.items():
        np.save(CACHE / f"{name}.npy", x)
    (CACHE / "ids.json").write_text(json.dumps(ids))
    print({name: x.shape for name, x in views.items()})


if __name__ == "__main__":
    main()
