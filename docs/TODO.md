# TODO

Open work on the search app. Reasons and history are in `decisions.md`.

## Now

- [ ] Agree the contract between the index and the API (which fields every index keeps).
- [ ] Test the setup from a fresh clone on a second machine.
- [ ] Recheck the UI's example queries after any index change.

## Index

- [ ] Try BGE's recommended query prefix for short queries.
- [ ] Use LCC subclass labels in the embedded text, and fill the gaps in `lcc_outline.json`.
- [ ] Test adding LCSH subjects to passage documents.
- [ ] Plan a move off `langchain-community`, which is being sunset.

## Next

- [ ] Filters by bookshelf and LCC class.
- [ ] Browse by bookshelf on the home page.
- [ ] "Useful / not useful" feedback on results, saved as evaluation data.
- [ ] Dark mode.
- [ ] Decide whether to show a relevance cutoff (needs evaluation data first).
- [ ] Deploy: UI on Cloudflare, API on a separate host.

## Later

- [ ] Hybrid keyword + semantic search, as another backend.
- [ ] Typo tolerance and query routing.
- [ ] Turning constraints like "but not religion" into filters.
- [ ] A second-stage reranker.
- [ ] Title and author boosting.
