# TODO: search API and UI

Owners are suggestions. Check items off with the date and move them to Done.

## Now (before Tue Nov 17)

- [ ] Agree the API contract with Estee and George. Confirm every index keeps `gutenberg_id` in chunk metadata and decide whether to keep `doc_type` / `passage_index`. (Cedric, Estee, George)
- [ ] Fresh-clone dry run on a teammate's laptop: README steps, build the index, `uvicorn api.app:app`, the four example queries. (Cedric + one teammate)
- [ ] Write the UI/API section of the weekend writeup for Charlene, drawing on `docs/decisions.md`. Cover the contract, why it's embedding-agnostic, why the raw score is kept, the labeling decisions, and the open questions below. (Cedric)
- [ ] Recheck `EXAMPLES` in `web/app.js` after any index change. (whoever changes the index)
- [ ] One slide on the API + UI for Tuesday: what's different from OpenSquare (embedding-agnostic API, cards from `data/books/`, "Why this book", URL state, faster load). Draft by midday Mon Nov 16. (Cedric)
- [ ] Run the live demo. Restart the laptop first and check the demo works from a cold start. Prep demo queries ahead, from Estee's test set and `evaluation/queries.csv`. (Cedric)
- [ ] "Why this book" was flagged as misleading at the team sync: "Your words also appear in" is literal word overlap, and next to a semantic score it reads like the model's reason. Decide whether to cut it, relabel it, or replace it with something semantic. (Cedric)
- [ ] Optional: deploy on Cloudflare free tier so Charlene can try it before Tuesday. Not promised. (team)

## Notes for the index team (found while wiring the API, not fixed here)

- [ ] The optional `embedding/extract_locc.py` outline scraper needs explicit `requests` and `pdfplumber` dependencies. The existing outline is committed, so this script isn't needed to build or search the index. (Estee)
- [ ] BGE-base expects the query prefix "Represent this sentence for searching relevant passages: " for short queries. It's a free experiment: `SEARCH_QUERY_PREFIX=... uvicorn api.app:app`, then compare the example queries. (Estee or George)
- [ ] `search_test.search_books` over-fetches `top_k * 5` chunks, which can return fewer than k books. The API's dedupe already handles this, so only the script is affected. (Estee)
- [ ] `preprocess._extract_locc_label` leaves `label` unbound when a code isn't in the map (crash), and only uses the top class, so "BV" embeds as "Philosophy. Psychology. Religion". It could reuse `api.books.lcc_label`, which has the subclass supplement. (Estee)
- [ ] `lcc_outline.json` misses the D subclasses DJ to DX and truncates HN and Z (scraped from the first PDF page only). The supplement lives in `api/books.py`. Better to fix the outline. (Estee)
- [ ] Summary docs embed `topic_subjects` merged with bookshelves, but passage docs only carry bookshelves. Worth testing whether passages need the LCSH too. (George)

## Next (after Charlene's feedback)

- [ ] Facet filters for bookshelf and LCC class, with counts, applied before ranking. Filtering is the benchmark's most praised feature, and filtered search helped 4 of 5 queries in our OpenSquare experiment. Needs a `filters` param in `/api/search` and over-fetching in the backend. (Cedric + index team)
- [ ] Browse by bookshelf on the home page, for discovery without typing (George's rec, Gutenberg's strength). (Cedric)
- [ ] A small "useful / not useful" per result, logged to local JSONL, so critique sessions become eval data. Never required before search. (Cedric)
- [ ] Dark mode token set, contrast-checked against the dark surfaces. (Cedric)
- [ ] Decide with Charlene whether to show a relevance cutoff or a "weaker matches below" divider. Scores aren't calibrated, so this needs eval data first. (team)

## Later / out of UI scope (search-side recs, kept so nothing gets lost)

- [ ] Hybrid keyword + semantic (Recs). It would plug in as another backend in `api/searchers.py`.
- [ ] Typo tolerance and a query router (Recs: Estee, Jeff, Cedric).
- [ ] Negation and constraint parsing ("immigrants, but not religion") into metadata filters (Estee).
- [ ] A second-stage reranker (Estee).
- [ ] Title and author boosting (Recs: Cedric, Jeff).

## Done

- [x] 2026-11-15: API + UI pushed straight to main instead of a PR (58b4a80, 52726ac), and `api-ui` synced with main. Docs now say `127.0.0.1:8000`, since `localhost:8000` can collide with Docker. (Cedric)
- [x] 2026-11-13: Local setup on George's Mac: corrected requirement pin syntax without changing versions, installed into Python 3.13 `.venv`, built 6,896 vectors, passed 29 tests, and verified CLI/API parity for all four example queries. Saved an ignored local baseline; retrieval code is unchanged. (George)
- [x] 2026-11-12: Cloned `jeffgord/cds-capstone`, created branch `api-ui`, built Estee's index locally (6,896 vectors, ~1 min). (Cedric)
- [x] 2026-11-12: API (`api/`): health, search with book-level dedupe and paging, book detail, background model load, no-index state. Same books and scores as `search_test.py` for "peaceful diplomacy without military conflict". (Cedric)
- [x] 2026-11-12: UI (`web/`): Gutenberg-based visual guideline, search guide, result rows, "Why this book", detail panel, recent searches, URL state, and all error states. Screenshots checked at 1280px and 390px. (Cedric)
- [x] 2026-11-12: 29 API tests with a fake searcher (`tests/test_api.py`). (Cedric)
