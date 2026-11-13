# API

A small FastAPI server that answers search queries and serves the UI in `web/`. It doesn't care how the books were embedded: any index that can map a hit back to a `gutenberg_id` plugs in through one adapter in `searchers.py`. Everything a result card shows comes from `data/books/{id}.json`, not from the index, so the UI keeps working when the model, chunking or embedded fields change.

## Run it

From the repo root, with the virtual environment active:

```sh
pip install -r api/requirements.txt   # plus the root requirements for the index (faiss-cpu, langchain-*, sentence-transformers)
python test_script.py                 # builds gutenberg_faiss_test/ once (~1 minute, 6,896 vectors)
uvicorn api.app:app --reload          # http://localhost:8000
python -m pytest tests/               # no model or index needed
```

The server starts in about a second and loads the model in the background. Until it's ready, `/api/health` says `"loading": true` and the UI shows "Loading the search model". Without an index, the server still starts, and health and the UI say how to build one.

## Endpoints

### `GET /api/health`

```json
{ "ready": true, "loading": false, "error": null, "n_books": 1000,
  "searcher": "langchain-faiss", "model": "BAAI/bge-base-en-v1.5", "index_dir": "...",
  "n_vectors": 6896, "score_kind": "cosine", "query_prefix": null }
```

### `GET /api/search?q=&k=10&offset=0`

- `q` is trimmed and whitespace-collapsed; an empty `q` is a 400.
- `k` is 1 to 50 (larger values are clamped to 50). `offset` pages through results.
- Returns 503 while the model loads or when there's no index.

```json
{
  "query": "home remedies and herbal medicine", "k": 10, "offset": 0, "took_ms": 19,
  "has_more": true, "score_kind": "cosine", "highlight_terms": ["home", "remedi", "herbal", "medicine"],
  "results": [{
    "rank": 1, "gutenberg_id": 12345, "score": 0.6671,
    "matched_via": "passage", "passage_index": 2, "n_passages": 6,
    "snippet": "text from the book that matched...",
    "fields_matched": [{"field": "title", "terms": ["remedies"]}],
    "book": {
      "title": "...", "subtitle": null,
      "authors": [{"name": "Sylvain, Adrien, 1826-1914", "display": "Adrien Sylvain (1826-1914)", "role": "Author"}],
      "added_year": 2009, "description": "...", "subjects": ["..."], "topic_subjects": ["..."],
      "locc": [{"code": "BV", "label": "Practical Theology"}],
      "url": "https://www.gutenberg.org/ebooks/12345",
      "cover_url": "https://www.gutenberg.org/cache/epub/12345/pg12345.cover.medium.jpg"
    }
  }]
}
```

| Field | Meaning |
|---|---|
| `score` | Similarity from the backend, higher is closer. With the current index it's cosine similarity. It's only comparable within one search. |
| `matched_via` | The kind of chunk that matched: `"summary"` or `"passage"` in Estee's index, or `null` if the index doesn't say. |
| `passage_index` | Which entry of the book's `passages` matched, if the chunk was one. |
| `snippet` | Text to quote in "Why this book". It's the book's own text, never the embedded string with its "Title: ... \| Excerpt:" header. |
| `fields_matched` | Card fields that literally contain a query word (crude stemming). This is word overlap, not the model's reasoning, and the UI labels it that way. |
| `highlight_terms` | Word stems the UI highlights in snippets, using the same rule as `fields_matched`. |
| `added_year` | Year of the Gutenberg release (`issued`), not the original publication. |
| `description` | Gutenberg's auto-generated summary, or `null` (16 books have none). |
| `locc` | LoC classification code and readable label. Subclass labels come from `embedding/lcc_outline.json` plus `LCC_SUPPLEMENT` in `books.py` for subclasses the outline scrape missed. |

### `GET /api/books/{id}`

The card fields plus `table_of_contents`, `introduction`, `passages` and `has_text` (false for the 7 books with no extracted text). 404 for an unknown id.

## Plugging in a different index

A backend is any object with two methods (see `Searcher` in `searchers.py`):

```python
def search(self, query: str, n: int) -> list[ChunkHit]: ...  # up to n chunk hits, best first
def info(self) -> dict: ...                                     # shown by /api/health
```

`ChunkHit(gutenberg_id, score, doc_type=None, passage_index=None, text=None)`:
- **Required:** `gutenberg_id` and a `score` where higher is better. This is the one rule for index builders. If your chunks can't be mapped back to a book id, the API can't show them.
- **Optional:** `doc_type`, `passage_index` and `text` make the "Why this book" box more specific.
- Return raw chunk hits. **The API dedupes by book** (the best chunk wins) and asks for more chunks if dedupe leaves a page short, so backends don't need any dedupe logic.

For a LangChain FAISS index, nothing needs code. Point the env vars at it:

| Variable | Default | |
|---|---|---|
| `SEARCH_INDEX_DIR` | `gutenberg_faiss_test` | Folder with `index.faiss` + `index.pkl`, relative to the repo root |
| `SEARCH_MODEL` | `BAAI/bge-base-en-v1.5` | Must be the model the index was built with |
| `SEARCH_QUERY_PREFIX` | empty | Prepended to every query. BGE recommends `"Represent this sentence for searching relevant passages: "` for short queries (untested here, see `docs/TODO.md`) |

The adapter converts scores from the store's distance strategy. Inner product is already a similarity. Euclidean, and LangChain's `COSINE` (which it also stores as an L2 index), return squared L2 distance, which on normalized vectors is `2 - 2cos`, so the score becomes `1 - d/2`. That's the same conversion `search_test.py` uses, and the API returns the same books and scores as that script.

For anything else (a different vector store, a reranker, hybrid search later), write a class with `search()` and `info()` and return it from `load_searcher()`.

The index is a pickle, so `load_local` runs with `allow_dangerous_deserialization=True`. Only load indexes you built yourself. The folder is gitignored, so in this repo that's always the case.
