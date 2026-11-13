# TODO: search API and UI

Owners are suggestions. Check items off with the date and move them to Done.

## Now (before Tue Nov 17)

- [ ] Agree the API contract with Estee and George. Confirm every index keeps `gutenberg_id` in chunk metadata and decide whether to keep `doc_type` / `passage_index`. (Cedric, Estee, George)
- [ ] Push branch `api-ui` and open a PR to main once the team's had a look. (Cedric)
- [ ] Fresh-clone dry run on a teammate's laptop: README steps, build the index, `uvicorn api.app:app`, the four example queries. (Cedric + one teammate)
- [ ] Write the UI/API section of the weekend writeup for Charlene, drawing on `docs/decisions.md`. Cover the contract, why it's embedding-agnostic, why the raw score is kept, the labeling decisions, and the open questions below. (Cedric)
- [ ] Recheck `EXAMPLES` in `web/app.js` after any index change. (whoever changes the index)

## Notes for the index team (found while wiring the API, not fixed here)

- [ ] The root `requirements.txt` is `pip list` output ("faiss-cpu   1.16.0"), so `pip install -r` fails. It needs `==` pins. `embedding/extract_locc.py` also needs `requests` and `pdfplumber`, which aren't listed. (Estee)
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

- [x] 2026-11-12: Cloned `jeffgord/cds-capstone`, created branch `api-ui`, built Estee's index locally (6,896 vectors, ~1 min). (Cedric)
- [x] 2026-11-12: API (`api/`): health, search with book-level dedupe and paging, book detail, background model load, no-index state. Same books and scores as `search_test.py` for "peaceful diplomacy without military conflict". (Cedric)
- [x] 2026-11-12: UI (`web/`): Gutenberg-based visual guideline, search guide, result rows, "Why this book", detail panel, recent searches, URL state, and all error states. Screenshots checked at 1280px and 390px. (Cedric)
- [x] 2026-11-12: 29 API tests with a fake searcher (`tests/test_api.py`). (Cedric)
