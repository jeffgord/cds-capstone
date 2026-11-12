# Ingestion

`ingest.py` downloads a random subset of English nonfiction books from Project Gutenberg and writes one file per book to `data/books/{id}.json`. Run it from the repo root with the virtual environment activated:

```sh
python ingestion/ingest.py            # 1,000 books (~25 minutes the first time)
python ingestion/ingest.py --limit 50 # a quick sample
```

The subset order is fixed, so a larger `--limit` keeps the same books and adds more. Each run clears and rewrites `data/books/`, which is committed so the dataset is ready to use without running anything.

## Fields

Each file is one flat record combining the book's catalog metadata with text extracted from the book itself. The text fields are kept separate so the embedding side can choose what to use and how to combine it with the metadata. Missing parts are `null` or `[]`. Prose is unwrapped to one paragraph per line, with title pages, digitization credits, page markers and page numbers removed.

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

In the 1,000-book dataset, 672 books have a table of contents, 633 an introduction, 94 a conclusion and 210 index terms; 971 have all six passages. Seven books (copyright registers, a list of post offices and four short Bible books) have no extracted text at all, only metadata.

## Raw data

`data/raw/` is not committed. It holds the Gutenberg catalog (`pg_catalog.csv` and the RDF archive) and `summaries.json`, the book summaries pulled out of the RDF archive on the first run. Delete `summaries.json` if you re-download the archive, or new books will have no summary.

Full book texts aren't saved by `ingest.py`; it downloads them each run and keeps only the extracts. To look at the source data, save some full texts first:

```sh
python ingestion/download_full_texts.py            # first 25 books of the subset
python ingestion/download_full_texts.py --limit 100
```

They go in `data/raw/full-texts/{id}.txt`. They're the same books, in the same order, that `ingest.py` uses, and `ingest.py` reads them from there instead of downloading them again.
