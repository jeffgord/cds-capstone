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

`ingestion/ingest.py` downloads a random subset of English nonfiction books from Project Gutenberg and writes them in the same shape as OpenSquare's ingestion output. It needs Python 3.9+. Set up a virtual environment once:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then, with the environment activated:

```sh
python ingestion/ingest.py            # 1,000 books (~25 minutes the first time)
python ingestion/ingest.py --limit 50 # a quick sample
```

It writes one file per book, `data/books/{id}.json`, with the book's catalog metadata and text extracted from the book itself in one flat record. The text fields are kept separate so the embedding side can choose what to use and how to combine it with the metadata. Missing parts are `null` or `[]`. Prose is unwrapped to one paragraph per line, with title pages, digitization credits, page markers and page numbers removed.

  | Field | Contents |
  |---|---|
  | `gutenberg_id` | Project Gutenberg ebook number (also the filename) |
  | `title`, `subtitle` | From the catalog |
  | `contributors` | List of `{name, role, order}`; role is "Author" unless the catalog says otherwise (Editor, Translator, ...) |
  | `language`, `issued` | Language code; `issued` is the Gutenberg release date, not the original publication date |
  | `description` | Gutenberg's auto-generated summary of the book (almost every book has one) |
  | `subjects` | Gutenberg "bookshelves": broad categories like "History - American" |
  | `topic_subjects` | Library of Congress subject headings |
  | `locc` | Library of Congress classification codes |
  | `url` | The book's page on gutenberg.org |
  | `table_of_contents` | List of chapter titles, without page numbers or "Chapter 1." labels |
  | `introduction` | About a page from the introduction, preface or foreword, if the book has one |
  | `passages` | Up to 6 short passages (~400 characters) from evenly spaced points through the book |
  | `conclusion` | About a page from a conclusion, afterword or epilogue, if the book has one (rare) |
  | `index_terms` | Top-level entries from the back-of-book index, sampled evenly across the alphabet, if there is one |

The two catalog files are cached in `data/raw/`, along with `summaries.json`, the book summaries pulled out of the RDF catalog on the first run (delete it if you re-download the catalog). Full book texts aren't saved by `ingest.py`; it downloads them each run and keeps only the extracts.

To look at the source data, save some full texts first:

```sh
python ingestion/download_full_texts.py            # first 25 books of the subset
python ingestion/download_full_texts.py --limit 100
```

They go in `data/raw/full-texts/{id}.txt`. They're the same books, in the same order, that `ingest.py` uses, and `ingest.py` reads them from there instead of downloading them again. The subset order is fixed, so a larger `--limit` keeps the same books and adds more. `data/books/` is committed so the dataset is ready to use without running anything; `data/raw/` is not.

## Updating the reference repo

To pull the latest upstream changes into `opensquare-reference/`:

```sh
git submodule update --remote opensquare-reference
```

Then commit the updated submodule pointer so everyone gets the same version.
