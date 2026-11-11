# AGENTS.md

## Layout

- `opensquare-reference/` — git submodule pointing at https://github.com/NYULibraries/KA-opensquare-research-project. Use it as a guide for this project; don't edit it.
- `ingestion/ingest.py` — single stdlib-only script that builds the Gutenberg dataset in OpenSquare's shape: `data/metadata/{id}.json` + `data/text-sample/{id}.txt` (OpenSquare's equivalent was `textual_information`). ID field is `gutenberg_id` (OpenSquare's was `isbnLibrary`). Run `python ingestion/ingest.py [--limit N]`.
- `ingestion/download_full_texts.py [--limit 25]` — saves full texts for the first N books of the same subset to `data/raw/full-texts/`, for inspecting the data. `ingest.py` reads from there when a text exists, otherwise downloads in memory without saving (user doesn't want all ~0.5 GB of texts locally, but does want some to look at). `download_full_texts.py` owns book selection (`wanted()`, `load_subset()`) and text fetching (`download_text()`); `ingest.py` imports them, so imports go one way only.
- `data/raw/` is gitignored; `data/metadata/` and `data/text-sample/` are committed so teammates get the dataset without running the scripts (~8 MB at 1,000 books). Rerun and commit them when ingestion changes. `data/raw/` holds the catalog CSV, the RDF archive and `full-texts/`. The output folders (`metadata/`, `text-sample/`) are wiped and rewritten on every run; `data/raw/` never is.
- Unlike OpenSquare (which prepended title, description, reviews and subjects to the text), `data/text-sample/` holds only text extracted from the book. The team plans its own embedding strategy and will combine text with metadata there. Note that OpenSquare's search only embeds the text, so anything not combined in won't be searchable.

## Ingestion decisions and gotchas

- Subset: English nonfiction (no LoC class P, no "fiction" or "Periodicals" subject headings, no volume 2+), ordered by a SHA-256 hash of the ID so raising `--limit` only adds books. Not ranked by downloads: the RDF download counts are 30-day counts and a block of ~35 Feb–Mar 2026 releases (IDs ~78000) all show ~24.5k downloads from what looks like bot traffic.
- Metadata comes from `pg_catalog.csv`; the auto-generated summary (`pgterms:marc520`) comes from the RDF archive, which takes ~20s to scan.
- Texts come from the xmission mirror (`{d}/{i}/{g}/{id}/{id}-0.txt`, falling back to `{id}.txt`). `gutenberg.pglaf.org` was ~6s per file; gutenberg.org asks bulk downloaders to use mirrors. ~1.5s per book including a 0.5s politeness delay.
- START/END markers vary: some files have a BOM before `***`, some use `****`, older ones say "THIS PROJECT GUTENBERG". Mirror files have no license footer.
- There is deliberately no "last page" fallback for the conclusion section: nonfiction tails are footnotes, indexes, bibliographies or appendices, too varied to filter.
- Text samples are cleaned for embedding: no section labels (they'd be shared tokens across every book), prose unwrapped to one paragraph per line, paragraphs under 20 words skipped (title pages, headings, separators) along with digitization credits ("Produced by", "Transcribed", emails), `[Page N]`/`[Footnote]`/`[Illustration]` markers and `_italic_` underscores removed. ToC entries lose page numbers, dot leaders and "Chapter 1." / "CHAP. II.--" labels; a ToC ends at 3+ blank lines or a `* * *` separator line. Roman numerals in ToC labels are matched uppercase only so words like "Mill." survive.
- Known leftovers not worth fixing: missing drop-cap first letters ("f all the various..."), ditto marks and "DESIGN NO. 1"-style lines in some ToCs.
- Don't use the `Gutenberg` PyPI package: archived, pins old rdflib/pyparsing, needs Berkeley DB.
- Redirected stdout is buffered; use `python -u` to watch a log file live.

## Reference repo notes

- Its ingestion is not one pipeline: `ingestion/ingestion_pipeline.py` only fetches metadata and merges subject headings. The rest (`download-pdfs.py`, `extract-text-from-pdfs`, `metadata_exporter.py`, `concat_text.py`) are standalone scripts with hardcoded Windows paths, run by hand in that order. Then `embedder/embedding_pipeline.py` builds the FAISS index.
- It embeds a per-book "profile" (description, reviews, subject headings, ToC, one intro page, one conclusion page), not full text. Chunk size is 128 *characters*.

## Setup

- Clone with `git clone --recurse-submodules <url>`, or after a plain clone run `git submodule update --init`. Otherwise `opensquare-reference/` is empty.
- To pull upstream updates to the reference repo: `git submodule update --remote opensquare-reference`, then commit the changed submodule pointer.
