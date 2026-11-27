"""Evaluate the new full-text FAISS index against sample_eval/seed_eval.jsonl.

Defaults to the full-text index ($SCRATCH/gutenberg_faiss_fulltext, including
full-text chunks) and writes results to sample_eval/eval_results_fulltext.json
without overwriting baseline results.
"""

from collections import defaultdict
import json
import os
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.searchers import best_per_book, load_searcher
from fulltext_sandbox.search_cli_fulltext_sandbox import (
    default_index_dir,
    load_enriched_books,
    render_snippet,
)

EVAL_PATH = ROOT_DIR / "sample_eval" / "seed_eval.jsonl"
RESULTS_PATH = ROOT_DIR / "sample_eval" / "eval_results_fulltext.json"


def load_eval_queries(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def evaluate_query(searcher, books: dict, row: dict, k: int = 10) -> dict:
    query = row["query"]
    expected_ids = set(row["expected_gutenberg_ids"])

    hits = list(best_per_book(searcher, query, k, keep=lambda gid: gid in books)[:k])
    returned_ids = [h.gutenberg_id for h in hits]

    first_rank = None
    winning_hit = None
    for idx, h in enumerate(hits, start=1):
        if h.gutenberg_id in expected_ids:
            first_rank = idx
            winning_hit = h
            break

    hit_at_5 = 1.0 if (first_rank is not None and first_rank <= 5) else 0.0
    hit_at_10 = 1.0 if (first_rank is not None and first_rank <= 10) else 0.0
    mrr_at_10 = (1.0 / first_rank) if first_rank is not None else 0.0

    top1 = hits[0] if hits else None
    top1_record = books.get(top1.gutenberg_id, {}) if top1 else {}

    return {
        "query_id": row.get("query_id", ""),
        "query_type": row.get("query_type", "unknown"),
        "query": query,
        "expected_gutenberg_ids": sorted(expected_ids),
        "first_rank": first_rank,
        "hit@5": hit_at_5,
        "hit@10": hit_at_10,
        "mrr@10": mrr_at_10,
        "winning_doc_type": winning_hit.doc_type if winning_hit else None,
        "winning_score": round(float(winning_hit.score), 4) if winning_hit else None,
        "top1_gutenberg_id": top1.gutenberg_id if top1 else None,
        "top1_title": top1_record.get("title", ""),
        "top1_doc_type": top1.doc_type if top1 else None,
        "top1_score": round(float(top1.score), 4) if top1 else None,
        "top1_snippet": render_snippet(top1_record, top1) if top1 else "",
        "returned_top5_ids": returned_ids[:5],
    }


def summarize(results: list[dict]) -> dict:
    def _agg(subset: list[dict]) -> dict:
        n = len(subset)
        if n == 0:
            return {"count": 0, "hit@5": 0.0, "hit@10": 0.0, "mrr@10": 0.0}
        return {
            "count": n,
            "hit@5": round(sum(r["hit@5"] for r in subset) / n, 4),
            "hit@10": round(sum(r["hit@10"] for r in subset) / n, 4),
            "mrr@10": round(sum(r["mrr@10"] for r in subset) / n, 4),
        }

    by_type = defaultdict(list)
    for r in results:
        by_type[r["query_type"]].append(r)

    return {
        "overall": _agg(results),
        "by_query_type": {qtype: _agg(rows) for qtype, rows in sorted(by_type.items())},
    }


def main() -> None:
    if not EVAL_PATH.exists():
        raise FileNotFoundError(f"Missing eval file: {EVAL_PATH}")

    if not os.environ.get("SEARCH_INDEX_DIR"):
        os.environ["SEARCH_INDEX_DIR"] = default_index_dir()

    queries = load_eval_queries(EVAL_PATH)
    books = load_enriched_books()
    searcher = load_searcher()

    results = [evaluate_query(searcher, books, row, k=10) for row in queries]
    summary = summarize(results)

    print(f"Index dir: {os.environ['SEARCH_INDEX_DIR']}")
    print("=== Overall Metrics (Full-Text Sandbox) ===")
    print(json.dumps(summary["overall"], indent=2))
    print("\n=== By Query Type ===")
    print(json.dumps(summary["by_query_type"], indent=2))

    misses = [r for r in results if r["hit@5"] == 0.0]
    print(f"\n=== Misses Outside Top 5 ({len(misses)}/{len(results)}) ===")
    for m in misses:
        print(
            f"- [{m['query_id']}] ({m['query_type']}) expected={m['expected_gutenberg_ids']} "
            f"rank={m['first_rank']} | top1={m['top1_gutenberg_id']} ({m['top1_title']}) "
            f"via {m['top1_doc_type']} [{m['top1_score']}]"
        )
        print(f"    Q: {m['query']}")

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_PATH.open("w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2, ensure_ascii=False)
    print(f"\nSaved detailed results to {RESULTS_PATH}")


if __name__ == "__main__":
    main()