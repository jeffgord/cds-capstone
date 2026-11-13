# cds-capstone

Semantic search over Project Gutenberg books, modelled on NYU Libraries' [OpenSquare research project](https://github.com/NYULibraries/KA-opensquare-research-project), which is included as a git submodule in `opensquare-reference/` for reference.

## Setup

Clone with `--recurse-submodules`, or `opensquare-reference/` will be an empty folder.

```sh
git clone --recurse-submodules https://github.com/jeffgord/cds-capstone.git   # or, after a plain clone: git submodule update --init
cd cds-capstone
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Data

`data/books/{id}.json` has one file per book for 1,000 English nonfiction books from Project Gutenberg. Each file combines catalog metadata (title, authors, Gutenberg's summary, subject headings) with text sampled from the book (table of contents, introduction, passages, conclusion, index terms).

See [ingestion/README.md](ingestion/README.md) for what each field contains and how to rebuild or extend the dataset.

## Search app

```sh
pip install -r api/requirements.txt
python test_script.py          # build the index once (~1 minute)
uvicorn api.app:app            # open http://localhost:8000
```

See [api/README.md](api/README.md) for the API and how to plug in a different index, [web/README.md](web/README.md) for the UI and its visual guideline, and [docs/](docs/) for the plan, decisions and TODO.
