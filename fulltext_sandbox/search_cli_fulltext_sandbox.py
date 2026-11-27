"""Search the full-text FAISS index in $SCRATCH from the terminal.

    SEARCH_INDEX_DIR="$SCRATCH/gutenberg_faiss_fulltext" python fulltext_sandbox/search_cli_fulltext_sandbox.py "query" -k 5
"""

import argparse
import json
import os
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.books import load_books as api_load_books
from api.books import snippet as api_snippet
from api.searchers import best_per_book, load_searcher

ENRICHED_BOOKS_DIR = ROOT_DIR / "data" / "enriched_books"


def default_index_dir() -> str:
    scratch_base = Path(os.environ.get("SCRATCH") or f"/scratch/{os.environ.get('USER', 'user')}")
    return str(scratch_base / "gutenberg_faiss_fulltext")


def load_enriched_books(books_dir: Path = ENRICHED_BOOKS_DIR) -> dict:
    """Load enriched books keyed by gutenberg_id (as int/str), falling back to api.books.load_books()."""
    if books_dir.exists():
        records: dict = {}
        for p in sorted(books_dir.rglob("*.json")):
            with p.open("r", encoding="utf-8") as f:
                book = json.load(f)
            gid = book.get("gutenberg_id")
            if gid is not None:
                records[gid] = book
                records[str(gid)] = book
        if records:
            return records
    return api_load_books()


def render_snippet(record: dict, hit) -> str:
    """Return a clean snippet for summary, passage, or full_text_chunk hits."""
    doc_type = getattr(hit, "doc_type", "")
    hit_text = (getattr(hit, "text", "") or "").strip()

    if doc_type == "full_text_chunk":
        if hit_text:
            return hit_text[:400] + ("..." if len(hit_text) > 400 else "")
        full_text = (record.get("full_text") or "").strip()
        if full_text:
            return full_text[:400] + ("..." if len(full_text) > 400 else "")

    try:
        return api_snippet(record, doc_type, getattr(hit, "passage_index", -1), hit_text)
    except Exception:
        if hit_text:
            return hit_text[:400] + ("..." if len(hit_text) > 400 else "")
        return (record.get("summary") or record.get("title") or "")[:400]


def main() -> None:
    parser = argparse.ArgumentParser(description="Semantic search over full-text Gutenberg index in $SCRATCH.")
    parser.add_argument("query", nargs="?", default="peaceful diplomacy without military conflict")
    parser.add_argument("-k", type=int, default=5, help="number of books to show (default 5)")
    parser.add_argument(
        "--index-dir",
        default=os.environ.get("SEARCH_INDEX_DIR") or default_index_dir(),
        help="path to FAISS index directory",
    )
    parser.add_argument(
        "--books-dir",
        type=Path,
        default=ENRICHED_BOOKS_DIR,
        help="directory containing enriched book JSON files",
    )
    args = parser.parse_args()

    os.environ["SEARCH_INDEX_DIR"] = args.index_dir
    books = load_enriched_books(args.books_dir)
    searcher = load_searcher()

    hits = list(best_per_book(searcher, args.query, args.k, keep=lambda gid: gid in books)[: args.k])
    for hit in hits:
        record = books[hit.gutenberg_id]
        title = record.get("title", "Untitled")
        print(f"[{hit.score:.3f}] {hit.gutenberg_id} | {title} (matched via: {hit.doc_type})")
        print(f"    -> {render_snippet(record, hit)}\n")


if __name__ == "__main__":
    main()