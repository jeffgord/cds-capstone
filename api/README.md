# API

A small FastAPI server that answers search queries and serves the UI in `web/`. It doesn't care how the books were embedded: any index that can map a hit back to a `gutenberg_id` plugs in through one adapter in `searchers.py`. Everything a result card shows comes from `data/books/{id}.json`, not from the index, so the UI keeps working when the model, chunking or embedded fields change.

## Run it

From the repo root, with the virtual environment active:

```sh
pip install -r api/requirements.txt   # plus the root requirements for the index (faiss-cpu, langchain-*, sentence-transformers)
python build_index.py                 # builds gutenberg_faiss_test/ once (~1 minute, 6,896 vectors)
uvicorn api.app:app --reload          # http://127.0.0.1:8000
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

### `GET /api/search?q=&shelf=&lcc=&k=10&offset=0`

- `q` is trimmed and whitespace-collapsed.
- `shelf` (optional) is a Gutenberg bookshelf name, e.g. `Politics`. `lcc` (optional) is a Library of Congress main class letter, e.g. `J` for Political Science; it matches every call number starting with that letter. Both filters can be used together.
- With `q`, the semantic results are limited to books matching the filters. Without `q`, it lists the matching books by title, with `score: null`, `snippet: null` and a `total` count; this works even while the model is loading. The response echoes `shelf`, `lcc` and `lcc_label` (the class name).
- An empty `q` with no filter is a 400.
- `k` is 1 to 50 (larger values are clamped to 50). `offset` pages through results.
- Returns 503 while the model loads or when there's no index.

```json
{
  "query": "home remedies and herbal medicine", "k": 10, "offset": 0, "took_ms": 19,
  "has_more": true, "score_kind": "cosine",
  "results": [{
    "rank": 1, "gutenberg_id": 12345, "score": 0.6671,
    "matched_via": "passage", "passage_index": 2, "n_passages": 6,
    "snippet": "text from the book that matched...",
    "book": {
      "title": "...", "subtitle": null,
      "authors": [{"name": "Sylvain, Adrien, 1826-1914", "display": "Adrien Sylvain (1826-1914)", "role": "Author"}],
      "added_year": 2009, "description": "...", "subjects": ["..."], "topic_subjects": ["..."],
      "locc": [{"code": "BV", "label": "Practical Theology"}],
      "url": "https://www.gutenberg.org/ebooks/12345",
      "cover_url": "/covers/12345.jpg"
    }
  }]
}
```

| Field | Meaning |
|---|---|
| `score` | Similarity from the backend, higher is closer. With the current index it's cosine similarity. It's only comparable within one search. |
| `matched_via` | The kind of chunk that matched: `"summary"` or `"passage"` in the current index, or `null` if the index doesn't say. |
| `passage_index` | Which entry of the book's `passages` matched, if the chunk was one. |
| `snippet` | Text to quote in "Why this book". It's the book's own text, never the embedded string with its "Title: ... \| Excerpt:" header. |
| `added_year` | Year of the Gutenberg release (`issued`), not the original publication. |
| `description` | Gutenberg's auto-generated summary, or `null` (16 books have none). |
| `locc` | LoC classification code and readable label. Subclass labels come from `embedding/lcc_outline.json` plus `LCC_SUPPLEMENT` in `books.py` for subclasses the outline scrape missed. |
| `classes` | The Library of Congress main classes of the book's call numbers, e.g. `{"code": "J", "label": "Political Science"}`, from `LCC_CLASSES` in `books.py`. Used for the result chips and the `lcc` filter. |
| `cover_url` | `/covers/{id}.jpg` when the cover was saved with `ingestion/download_covers.py`, otherwise the gutenberg.org URL. The UI falls back to Gutenberg's mirror, then a letter placeholder. |

### `GET /api/books/{id}`

The card fields plus `table_of_contents`, `introduction`, `passages` and `has_text` (false for the 7 books with no extracted text). 404 for an unknown id.

### `GET /api/books/{id}/why?q=&matched_via=&passage_index=`

The evidence behind "Why this book", computed when the box is opened so search stays fast (well under a second per book on CPU). Pass `matched_via` and `passage_index` from the search result. The search model scores each sentence of the result's `snippet` against the query.

```json
{ "gutenberg_id": 12345, "query": "women fighting for the right to vote", "took_ms": 60,
  "sentences": [{"text": "If the adult citizen, male or female, has a right to vote...", "score": 0.649}] }
```

- `sentences` joined with spaces give back the `snippet`, so the UI can highlight the best one in place.
- 400 for an empty `q`, 404 for an unknown id, 503 while the model loads, and 501 if the backend has no `similarity()`.

## Plugging in a different index

A backend is any object with two methods (see `Searcher` in `searchers.py`):

```python
def search(self, query: str, n: int) -> list[ChunkHit]: ...  # up to n chunk hits, best first
def info(self) -> dict: ...                                     # shown by /api/health
```

`ChunkHit(gutenberg_id, score, doc_type=None, passage_index=None, text=None)`:
- **Required:** `gutenberg_id` and a `score` where higher is better. This is the one rule for index builders. If your chunks can't be mapped back to a book id, the API can't show them.
- **Optional:** `doc_type`, `passage_index` and `text` make the "Why this book" box more specific.
- **Optional method:** `similarity(query, texts) -> list[float]`, the same score as `search` for each text. With it, `/api/books/{id}/why` works; without it, the UI shows the matched text without the breakdown. The LangChain adapter uses the index's own embedding model.
- Return raw chunk hits. **The API dedupes by book** (the best chunk wins) and asks for more chunks if dedupe leaves a page short, so backends don't need any dedupe logic.

For a LangChain FAISS index, nothing needs code. Point the env vars at it:

| Variable | Default | |
|---|---|---|
| `SEARCH_INDEX_DIR` | `gutenberg_faiss_test` | Folder with `index.faiss` + `index.pkl`, relative to the repo root |
| `SEARCH_MODEL` | `BAAI/bge-base-en-v1.5` | Must be the model the index was built with |
| `SEARCH_QUERY_PREFIX` | empty | Prepended to every query. BGE recommends `"Represent this sentence for searching relevant passages: "` for short queries (untested here) |

The adapter converts scores from the store's distance strategy. Inner product is already a similarity. Euclidean, and LangChain's `COSINE` (which it also stores as an L2 index), return squared L2 distance, which on normalized vectors is `2 - 2cos`, so the score becomes `1 - d/2`. `search_cli.py` searches through the same code, so the terminal and the API always agree.

For anything else (a different vector store, a reranker, hybrid search later), write a class with `search()` and `info()` and return it from `load_searcher()`.

The index is a pickle, so `load_local` runs with `allow_dangerous_deserialization=True`. Only load indexes you built yourself. The folder is gitignored, so in this repo that's always the case.

## Hosting the UI separately

Locally one `uvicorn` process serves both the API and `web/`, so there's no CORS and one command to run. For a deployment, the two can be split, e.g. the UI on Cloudflare Pages and the API wherever a Python process with the model can run:

- **UI:** upload `web/` as static files and set `apiBase` in `web/config.js` to the API's URL.
- **API:** set `CORS_ORIGINS` to the UI's origin (comma-separated for several), e.g. `CORS_ORIGINS=https://our-site.pages.dev uvicorn api.app:app --host 0.0.0.0`. Without it, no CORS headers are sent. The API still serves `web/` at `/` either way.
- The host needs about 2 GB of RAM (PyTorch plus BGE-base) and the index folder. The index is gitignored, so build it on the host with `python build_index.py` or copy it there.

