"""Prepare an ungraded, shuffled book-labeling worksheet from the current index."""

import argparse
import csv
import hashlib
import json
import random
import subprocess
from pathlib import Path

from api.books import BOOKS_DIR, load_books
from api.searchers import ChunkHit, Searcher, load_searcher

ROOT_DIR = Path(__file__).resolve().parent.parent
QUERY_FIELDS = {"query_id", "topic", "query_type", "intent_group", "split", "status", "query", "intent"}
LABEL_FIELDS = [
    "query_id", "query", "intent", "gutenberg_id", "title", "subjects",
    "auto_generated_summary", "table_of_contents", "retrieved_passage",
    "book_record", "gutenberg_url", "relevance", "assessor", "notes",
]


def read_queries(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if not QUERY_FIELDS.issubset(reader.fieldnames or []):
            raise ValueError(f"Queries must contain columns: {sorted(QUERY_FIELDS)}")
        queries = list(reader)
    seen_ids = set()
    for query in queries:
        if any(not query.get(field, "").strip() for field in QUERY_FIELDS):
            raise ValueError("Every query field must be filled in")
        if query["query_id"] in seen_ids:
            raise ValueError(f"Duplicate query ID: {query['query_id']}")
        seen_ids.add(query["query_id"])
    if not queries:
        raise ValueError("Provide at least one query")
    return queries


def candidate_books(searcher: Searcher, query: str, count: int, book_ids: set[int]) -> list[ChunkHit]:
    chunk_count = max(200, count * 8)
    while True:
        hits = searcher.search(query, chunk_count)
        best = {}
        for hit in hits:
            if hit.gutenberg_id in book_ids:
                best.setdefault(hit.gutenberg_id, hit)
        if len(best) >= count or len(hits) < chunk_count:
            return list(best.values())[:count]
        chunk_count *= 2


def label_row(query: dict[str, str], hit: ChunkHit, book: dict) -> dict:
    passages = book.get("passages") or []
    passage_index = hit.passage_index
    passage = passages[passage_index] if passage_index is not None and 0 <= passage_index < len(passages) else ""
    return {
        "query_id": query["query_id"], "query": query["query"], "intent": query["intent"],
        "gutenberg_id": hit.gutenberg_id, "title": book["title"],
        "subjects": "; ".join(dict.fromkeys((book.get("topic_subjects") or []) + (book.get("subjects") or []))),
        "auto_generated_summary": book.get("description") or "",
        "table_of_contents": "; ".join(book.get("table_of_contents") or []),
        "retrieved_passage": passage,
        "book_record": f"data/books/{hit.gutenberg_id}.json",
        "gutenberg_url": book.get("url") or f"https://www.gutenberg.org/ebooks/{hit.gutenberg_id}",
        "relevance": "", "assessor": "", "notes": "",
    }


def dataset_hash() -> str:
    digest = hashlib.sha256()
    for path in sorted(BOOKS_DIR.glob("*.json")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, default=ROOT_DIR / "evaluation/queries.csv")
    parser.add_argument("--output-dir", type=Path, default=ROOT_DIR / "evaluation/pilot")
    parser.add_argument("--candidates", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20261113)
    args = parser.parse_args()
    if args.candidates < 1:
        parser.error("--candidates must be positive")
    if args.output_dir.exists():
        parser.error("Output directory already exists; choose a new directory to preserve existing judgments")
    queries = read_queries(args.queries)
    books = load_books()
    searcher = load_searcher()
    rows, runs = [], []
    for query in queries:
        hits = candidate_books(searcher, query["query"], args.candidates, set(books))
        runs.append({
            "query_id": query["query_id"],
            "hits": [
                {"rank": rank, "gutenberg_id": hit.gutenberg_id, "score": hit.score,
                 "doc_type": hit.doc_type, "passage_index": hit.passage_index}
                for rank, hit in enumerate(hits, start=1)
            ],
        })
        shuffled = list(hits)
        random.Random(f"{args.seed}:{query['query_id']}").shuffle(shuffled)
        rows.extend(label_row(query, hit, books[hit.gutenberg_id]) for hit in shuffled)
        print(f"{query['query_id']}: {len(hits)} unique candidate books")

    info = searcher.info()
    index_file = Path(info["index_dir"]) / "index.faiss"
    manifest = {
        "purpose": "Pilot development pool; no human judgments or held-out test results yet",
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT_DIR, text=True).strip(),
        "searcher": info, "dataset_sha256": dataset_hash(),
        "index_sha256": hashlib.sha256(index_file.read_bytes()).hexdigest(),
        "candidate_count": args.candidates, "shuffle_seed": args.seed,
        "queries": queries, "runs": runs,
    }
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with (args.output_dir / "labels.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=LABEL_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (args.output_dir / "run.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"Saved {len(rows)} ungraded rows to {args.output_dir / 'labels.csv'}")


if __name__ == "__main__":
    main()
