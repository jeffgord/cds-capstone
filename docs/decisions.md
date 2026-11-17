# Decisions: search API and UI

The app is a proof of concept for semantic search over a library collection: 1,000 English nonfiction books from Project Gutenberg (`data/books/`). An index turns parts of each book into vectors with an embedding model (`build_index.py`). The API (`api/`) answers searches against that index, and the web page (`web/`) shows the results.

This file records the main design decisions behind the API and UI: what, why, and what we gave up. Newest last. UI design rules are in `web/README.md`; the API contract is in `api/README.md`.

**The API is embedding-agnostic. Backends return chunk hits; the API does the rest.**
- **Why:** The index (model, chunking and embedded fields) is expected to change. If the UI read display data from the index, every index change would break it. The API asks a backend only for `(gutenberg_id, score)` plus optional `doc_type`, `passage_index` and `text`, and builds every card from `data/books/*.json`.
- **Gave up:** showing index-only data (like the exact embedded string) on cards.

**Dedupe by book happens in the API, not the backend.**
- **Why:** The index has up to 7 vectors per book (1 summary + 6 passages). Deduping a fixed `top_k * 5` over-fetch can return fewer than k books. The API keeps each book's best chunk and doubles the chunk request until the page is full, so any backend gets correct paging for free.
- **Gave up:** a little latency on deep pages (still under 0.6s on CPU).

**Semantic only, with no keyword backend.**
- **Why:** Semantic search is the focus of this project.
- **Gave up:** a dev fallback that runs without building an index. Building the index takes about a minute, and without one the UI shows the build command. Hybrid search stays possible later as just another backend.

**The raw score stays, with no percentage and no cutoff.**
- **Why:** Scores aren't calibrated across queries (a nonsense query can still score around 0.4), so a percentage or threshold would claim more than we know. The score sits on the "Why this book" button with a one-line note on how to read it.
- **Gave up:** an "out of 100" display and a relevance cutoff. The cutoff stays an open question until there's evaluation data.

**"Why this book" explains with facts we actually have.** (Replaced, see "'Why this book' is semantic" below.)
- **Why:** Search results that come with no explanation are hard to trust. We show:
  - which part of the book matched (summary or passage N), from the backend
  - the matched text with shared words highlighted
  - which card fields literally contain the query words
- **Gave up:** a generated (LLM) explanation. It can confidently explain a bad match, and it's out of scope.

**The visual base is gutenberg.org's own stylesheet.**
- **Why:** It should look like Gutenberg, just more searchable. The palette, Open Sans, pill search, parchment band and red section rules come from `gutenberg-globals.css` (gutenbergtools/gutenbergsite). What changes are common problems in library search pages: summaries in results, explanations, wrapping tags, no walls of text.
- **Gave up:** a distinct identity of our own.

**Light mode only.**
- **Why:** Kept simple for the first version. Tokens are on `:root`, so dark mode is one more token block.
- **Gave up:** dark mode for now.

**Covers are served from our own copy, with gutenberg.org as a fallback.**
- **Why:** Covers make results easy to scan, and gutenberg.org goes down for maintenance now and then. `ingestion/download_covers.py` saves every cover once from Gutenberg's mirror to `data/raw/covers/` (not committed, about 18 MB), and the API serves them at `/covers/{id}.jpg`. Without that folder, covers load from gutenberg.org, then its mirror.
- **Gave up:** a calmer page (the auto-generated pattern covers are loud). The letter placeholder covers books with no cover.

**Vanilla HTML/CSS/JS served by FastAPI.**
- **Why:** No build step, one command (`uvicorn api.app:app`), same origin so no CORS. It's small enough (~500 lines of JS) that a framework would add more than it saves. Streamlit was ruled out because it reruns the script on every click and makes hover, focus and URL state hard.
- **Gave up:** components and type checking. Revisit if the UI grows past one page.

**The URL is the one source of truth for UI state.**
- **Why:** Back and forward always work, the search box always shows the current query, and every view can be shared as a link.
- **Gave up:** nothing.

**Data labeling: "Added to Gutenberg" and "auto-generated summary".**
- **Why:**
  - `issued` is the Gutenberg release date, not the publication date.
  - The `description` field is Gutenberg's machine-generated summary. 59 of 1,000 hedge with "likely written in...", and 16 are empty.
  - A metadata librarian will catch either mislabel.
- **Gave up:** a "published" year on cards. The author's life dates now carry the age of the book.

**Author names are shown in reading order.**
- **Why:** Catalog form ("Sylvain, Adrien, 1826-1914") is hard to scan. `display_name()` handles all 1,206 contributor names in the dataset, including Sir, peers, saints, post-nominals and open dates. Cases are pinned in `tests/test_api.py`.
- **Gave up:** nothing. The raw `name` is still in the API.

**"Why this book" is semantic, not word overlap.**
- **Why:** Now the search model itself scores each sentence of the matched text and highlights the closest one. It's computed on open via `/api/books/{id}/why`, so search stays ~20 ms.
- **Gave up:** `fields_matched` and `highlight_terms` in the API (removed, nothing else used them), and an instant highlight: it appears a moment after the box opens. Backends without `similarity()` show the plain quote.

**The UI can be hosted apart from the API; locally it's still one process.**
- **Why:** We plan to put the UI on Cloudflare, and the free Cloudflare tiers can't run a Python process with PyTorch and BGE. So the UI goes on Pages and the API somewhere else. That needs `apiBase` in `web/config.js` and `CORS_ORIGINS` on the API (~20 lines). Same origin serving stays the default for local runs: one command, no CORS.
- **Gave up:** nothing for local use. A deployment needs two hosts to keep in sync.

**Bookshelves are a filter, not a keyword search.**
- **Why:** Clicking a Gutenberg bookshelf narrows the results to books on that shelf, using the catalog's own shelf list. With a search, the shelf's books are still ranked by the semantic score; without one, they're listed by title. Search itself stays purely semantic.
- **Gave up:** nothing. The same `keep` filter in `best_per_book()` can later serve LCC or subject filters.
