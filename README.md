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
python test_script.py          # build once; first run also downloads the embedding model
python search_test.py          # try the example query in the terminal
uvicorn api.app:app            # open http://localhost:8000
```

See [embedding/README.md](embedding/README.md) for the pipeline, [api/README.md](api/README.md) for the API and how to plug in a different index, [web/README.md](web/README.md) for the UI, and [docs/](docs/) for the plan, decisions and TODO.
