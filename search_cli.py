"""Search the index from the terminal, through the same code as the API (api/searchers.py), so the two
always agree. Build the index first with: python build_index.py

    python search_cli.py "home remedies and herbal medicine" -k 5
"""
import argparse

from api.books import load_books, snippet
from api.searchers import best_per_book, load_searcher


def main():
    parser = argparse.ArgumentParser(description="Semantic search over data/books from the terminal.")
    parser.add_argument("query", nargs="?", default="peaceful diplomacy without military conflict")
    parser.add_argument("-k", type=int, default=5, help="number of books to show (default 5)")
    args = parser.parse_args()

    books = load_books()
    searcher = load_searcher()  # same env vars as the API: SEARCH_INDEX_DIR, SEARCH_MODEL, SEARCH_QUERY_PREFIX
    for hit in best_per_book(searcher, args.query, args.k, keep=lambda gid: gid in books)[:args.k]:
        record = books[hit.gutenberg_id]
        print(f"[{hit.score:.3f}] {hit.gutenberg_id} | {record['title']} (matched via: {hit.doc_type})")
        print(f"    -> {snippet(record, hit.doc_type, hit.passage_index, hit.text)}\n")


if __name__ == "__main__":
    main()
