# Plan: embedding-agnostic search API + Gutenberg-styled UI

Owner: Cedric. Written 2026-11-12, for the Tue Nov 17 critique with Charlene. Status per item is in `TODO.md`; reasons are in `decisions.md`.

## Context

At the Nov 10 meeting Charlene gave the team full autonomy to build our own semantic search pipeline, with Gutenberg as the corpus. The work split three ways:
- Jeff: the dataset, 1,000 books in `data/books/`.
- Estee and George: the search index. Estee's first version uses BGE-base + FAISS with summary and passage docs.
- Cedric: the UI and the API it needs.

Charlene's role is now critic and sponsor. The deliverable is a locally hosted proof of concept with a UI that reflects the team's recommendations.

## Goal

A skeleton others can build on. The API defines what the UI needs and nothing about how books are embedded, so the index team can change the model, chunking or fields without touching the UI. The search is purely semantic, which is the focus Charlene set. Keyword search can come later as another backend.

## Weakest assumption

Every future index can return, per hit, at least a `gutenberg_id` and a score. If an index can't map chunks back to book ids, no adapter can fix that, so it's the one rule in `api/README.md`.

## What gets built

- **`api/`**:
  - `searchers.py` has the `Searcher` protocol and `ChunkHit`, plus a LangChain FAISS adapter configured by env vars.
  - `app.py` holds the endpoints. It dedupes by book, pages results and loads the model in the background.
  - `books.py` builds cards and snippets, formats author names and LCC labels, and computes word overlap.
- **`web/`:** one page, vanilla JS, served by the API. It has the search guide, result rows, the "Why this book" box, the detail panel, recent searches, URL state, and all error states.
- **`docs/`:** this plan, `decisions.md` and `TODO.md`.
- **`tests/`:** contract tests with a fake searcher.

## Visual direction

Use gutenberg.org's own template (parchment band, Open Sans, teal pill search, red section rules, bold-title result rows) so it reads as part of the Gutenberg family, and fix what our critiques of other library sites found:
- summaries in the results
- explanations for matches
- capped, wrapping tags
- no picker for the number of results
- a search guide on the home page
- a working back button

Light mode only for now. Full rules are in `web/README.md`.

## Verification

- `python -m pytest tests/`
- With the real index, `/api/search` returns the same books and scores as `search_test.py`.
- Headless screenshots at 1280px and 390px: home, results, "Why this book" open, and the panel open. Also the no-index and API-down states.
- A keyboard-only pass.
- A fresh-clone run on a teammate's laptop before Tuesday.
