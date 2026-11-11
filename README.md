# cds-capstone

## Getting started

This repo includes [KA-opensquare-research-project](https://github.com/NYULibraries/KA-opensquare-research-project) as a git submodule in `opensquare-reference/`, which we use as a reference for our work. Clone with submodules so that folder isn't empty:

```sh
git clone --recurse-submodules <repo-url>
```

If you already cloned without that flag, run:

```sh
git submodule update --init
```

## Building the dataset

`ingestion/ingest.py` downloads a random subset of English nonfiction books from Project Gutenberg and writes them in the same shape as OpenSquare's ingestion output. It needs only Python 3.9+ (no packages):

```sh
python ingestion/ingest.py            # 1,000 books (~25 minutes the first time)
python ingestion/ingest.py --limit 50 # a quick sample
```

It writes, for each book:

- `data/metadata/{id}.json`: bibliographic metadata (title, contributors, Gutenberg summary, subject headings), keyed by `gutenberg_id`
- `data/text-sample/{id}.txt`: sections extracted from the book itself: the table of contents (one chapter title per line), then about a page of the introduction (or of the opening, if there's no introduction), then a page of the conclusion when there is one. Sections are separated by a blank line and have no labels. Prose is unwrapped to one paragraph per line, and title pages, digitization credits, page markers and page numbers are removed. No metadata is repeated here; combine it with the JSON however your embedding approach needs.

The two catalog files are cached in `data/raw/`. Full book texts aren't saved by `ingest.py`; it downloads them each run and keeps only the extracts.

To look at the source data, save some full texts first:

```sh
python ingestion/download_full_texts.py            # first 25 books of the subset
python ingestion/download_full_texts.py --limit 100
```

They go in `data/raw/full-texts/{id}.txt`. They're the same books, in the same order, that `ingest.py` uses, and `ingest.py` reads them from there instead of downloading them again. The subset order is fixed, so a larger `--limit` keeps the same books and adds more. `data/metadata/` and `data/text-sample/` are committed so the dataset is ready to use without running anything; `data/raw/` is not.

## Updating the reference repo

To pull the latest upstream changes into `opensquare-reference/`:

```sh
git submodule update --remote opensquare-reference
```

Then commit the updated submodule pointer so everyone gets the same version.
