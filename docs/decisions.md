# Decisions: search API and UI

One entry per decision: what, why, what we gave up, and where it came from. Newest last. UI design rules are in `web/README.md`; the API contract is in `api/README.md`.

Sources:
- Meeting 11/10: the Charlene meeting notes
- Recs: `Capstone Meeting Notes 11_3`
- Bench: `Homework 10_26: Competitive Benchmarking` and `Homework 10_12` slides
- App: `Semantic Book Search App Feedback`

## 2026-11-12

**The API is embedding-agnostic. Backends return chunk hits; the API does the rest.**
- **Why:** Estee and George own the index and will change the model, chunking and fields. If the UI read display data from the index, every index change would break it. The API asks a backend only for `(gutenberg_id, score)` plus optional `doc_type`, `passage_index` and `text`, and builds every card from `data/books/*.json`.
- **Gave up:** showing index-only data (like the exact embedded string) on cards.
- **Source:** Meeting 11/10 work split ("expose search index via API", "frontend client for the API").

**Dedupe by book happens in the API, not the backend.**
- **Why:** Estee's index has up to 7 vectors per book (1 summary + 6 passages). `search_test.py` dedupes with a fixed `top_k * 5` over-fetch, which can return fewer than k books. The API keeps each book's best chunk and doubles the chunk request until the page is full, so any backend gets correct paging for free.
- **Gave up:** a little latency on deep pages (still under 0.6s on CPU).

**Semantic only, with no keyword backend.**
- **Why:** Charlene sees semantic search as the focus. Keyword search was only added to OpenSquare because of colleague pushback (Meeting 11/10).
- **Gave up:** a dev fallback that runs without building an index. Building the index takes about a minute, and without one the UI shows the build command. Hybrid search stays possible later as just another backend.

**The raw score stays, with no percentage and no cutoff.**
- **Why:** Charlene wants score transparency for Phase 2 evaluation (Meeting 11/10). Scores aren't calibrated across queries (App/Recs: gibberish scored 0.38 on OpenSquare), so a percentage or threshold would claim more than we know. The score sits on the "Why this book" button with a one-line note on how to read it.
- **Gave up:** the team's "out of 100" and "relevance cutoff" recs (Jeff, George). The cutoff is an open question for Charlene.

**"Why this book" explains with facts we actually have.**
- **Why:** The top complaint about OpenSquare was no explanation (App, Recs: every teammate). We show:
  - which part of the book matched (summary or passage N), from the backend
  - the matched text with shared words highlighted
  - which card fields literally contain the query words
- **Gave up:** a generated explanation (George's LLM idea). It can confidently explain a bad match, and it's out of scope.

**The visual base is gutenberg.org's own stylesheet.**
- **Why:** Cedric asked for it to look like Gutenberg, not sloppy, just more searchable. The palette, Open Sans, pill search, parchment band and red section rules come from `gutenberg-globals.css` (gutenbergtools/gutenbergsite). Our critiques decide what changes: summaries in results, explanations, wrapping tags, no walls of text.
- **Gave up:** a distinct identity of our own.

**No PG logo, a working name, and a non-affiliation footer.**
- **Why:** "Project Gutenberg" is a trademark and we're a prototype.
- **Gave up:** nothing real. The name "Gutenberg Semantic Search" is a placeholder the team can change in `index.html`.

**Light mode only.**
- **Why:** Cedric's call for now. Tokens are on `:root`, so dark mode is one more token block.
- **Gave up:** dark mode for the Tuesday demo.

**Covers are hotlinked from gutenberg.org.**
- **Why:** OpenSquare's covers made results easy to scan (Bench: "Results include relevant metadata, summary and book cover"). About 10 lazy images per page is ordinary browsing traffic.
- **Gave up:** offline covers (the letter fallback covers that case) and a calmer page. The auto-generated pattern covers are loud.

**Vanilla HTML/CSS/JS served by FastAPI.**
- **Why:** No build step, one command (`uvicorn api.app:app`), same origin so no CORS. It's small enough (~500 lines of JS) that a framework would add more than it saves. Streamlit was ruled out because it reruns the script on every click and makes hover, focus and URL state hard. We fought that in the OpenSquare app.
- **Gave up:** components and type checking. Revisit if the UI grows past one page.

**The URL is the one source of truth for UI state.**
- **Why:** Fixes "no option to go back to previous search" and "query doesn't clear out properly" (App), and makes every view linkable for the writeup and for Charlene.
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

**LCC labels use subclasses, plus a supplement.**
- **Why:** `embedding/lcc_outline.json` was scraped from the first page of each LoC PDF. It misses the D subclasses DJ to DX (so DS "Asia" showed as "World History and History of Europe") and truncates HN and Z. `LCC_SUPPLEMENT` in `api/books.py` fills those from the LoC outline. Full call numbers like `D501` map by their letters.
- **Gave up:** nothing. Tell Estee so `preprocess.py` can use the same labels for embedding.

**The four example queries were checked against the index.**
- **What:** "peaceful diplomacy without military conflict", "daily life of pioneer settlers on the American frontier", "home remedies and herbal medicine", "women fighting for the right to vote".
- **Why:** Each one's top 3 is on topic with Estee's BGE-base index. "how to keep bees and harvest honey" was dropped because #3 was "Are the Effects of Use and Disuse Inherited?".
- **Gave up:** nothing. Recheck whenever the index changes.

**Work lives on branch `api-ui`, not main.**
- **Why:** Estee is committing to main, and George may add his own API. Everything new sits in `api/`, `web/`, `docs/` and `tests/`, plus a few lines in `AGENTS.md` and the root README, so merging is trivial.
- **Gave up:** teammates getting it on `git pull` until it's merged.
