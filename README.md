# cds-capstone

Semantic search over Project Gutenberg books, modelled on NYU Libraries' [OpenSquare research project](https://github.com/NYULibraries/KA-opensquare-research-project), which is included as a git submodule in `opensquare-reference/` for reference.

## Setup

Use Python 3.13 for the setup below. Clone with `--recurse-submodules`, or `opensquare-reference/` will be an empty folder.

```sh
git clone --recurse-submodules https://github.com/jeffgord/cds-capstone.git   # or, after a plain clone: git submodule update --init
cd cds-capstone
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Data

`data/books/{id}.json` has one file per book for 1,000 English nonfiction books from Project Gutenberg. Each file combines catalog metadata (title, authors, Gutenberg's summary, subject headings) with text sampled from the book (table of contents, introduction, passages, conclusion, index terms).

See [ingestion/README.md](ingestion/README.md) for what each field contains and how to rebuild or extend the dataset.

## Search app

```sh
pip install -r api/requirements.txt
python build_index.py          # build once; first run also downloads the embedding model
python ingestion/download_covers.py  # optional: save covers locally (~11 min, ~18 MB)
python search_cli.py "query"  # search from the terminal (same code as the API)
uvicorn api.app:app            # open http://127.0.0.1:8000
```

### How search works

1. **Build the index once.** `build_index.py` turns each book into text documents, embeds them with `BAAI/bge-base-en-v1.5`, and saves the 6,896 vectors to `gutenberg_faiss_test/` (about a minute). Rerun it only when the data or what gets embedded changes.
   - 1 summary document per book: title, authors, subjects (bookshelves and LCSH), LCC class and Gutenberg's summary.
   - Up to 6 passage documents per book: title, bookshelves and ~400 characters of the book's text.
   - Not embedded: table of contents, introduction, conclusion, index terms.
2. **Start the server.** `uvicorn` loads the model and the saved index into memory. Nothing is re-embedded at startup.
3. **Each search** embeds only the query, with the same model. FAISS finds the closest documents, the API keeps each book's best match, and the result cards come from `data/books/`, not from the index.
4. **"Why this book"** runs the model again when you open it. It scores each sentence of the matched text to find the closest one. The index only holds whole documents, not single sentences.

See [embedding/README.md](embedding/README.md) for the pipeline, [api/README.md](api/README.md) for the API and how to plug in a different index, [web/README.md](web/README.md) for the UI, and [docs/](docs/) for the decision log and open work.
