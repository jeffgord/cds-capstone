"""Build combined book JSON records containing metadata, extracted samples, and full_text.

Reads existing records from data/books/{id}.json (when present) and cleaned full texts
from data/cleaned/full-texts/{id}.txt, writing combined records to data/enriched_books/{id}.json
without modifying ingest.py or overwriting data/books/.

Usage:
    python ingestion/build_fulltext_records_sandbox.py
"""

import csv
import json
import sys
from pathlib import Path

from tqdm import tqdm

INGEST_DIR = Path(__file__).resolve().parent
if str(INGEST_DIR) not in sys.path:
    sys.path.insert(0, str(INGEST_DIR))

from download_full_texts import DATA, RAW  # noqa: E402
from ingest import BOOKS, build_metadata, load_summaries  # noqa: E402

CLEANED_TEXTS = DATA / "cleaned" / "full-texts"
ENRICHED_BOOKS = DATA / "enriched_books"


def load_catalog_by_id() -> dict[int, dict[str, str]]:
    catalog_path = RAW / "pg_catalog.csv"
    if not catalog_path.exists():
        return {}
    with open(catalog_path, encoding="utf-8", newline="") as f:
        return {int(row["Text#"]): row for row in csv.DictReader(f) if row.get("Text#")}


def main() -> None:
    if not CLEANED_TEXTS.exists():
        print(f"Cleaned texts directory not found: {CLEANED_TEXTS}", flush=True)
        return

    ENRICHED_BOOKS.mkdir(parents=True, exist_ok=True)
    text_files = sorted(CLEANED_TEXTS.glob("*.txt"), key=lambda p: int(p.stem))
    if not text_files:
        print(f"No cleaned .txt files found in {CLEANED_TEXTS}", flush=True)
        return

    catalog_by_id = load_catalog_by_id()
    summaries = load_summaries() if (RAW / "summaries.json").exists() else {}

    written = missing_json_fallback = 0
    for txt_path in tqdm(text_files, unit="book"):
        book_id = int(txt_path.stem)
        full_text = txt_path.read_text(encoding="utf-8").strip()
        existing_json = BOOKS / f"{book_id}.json"

        if existing_json.exists():
            record = json.loads(existing_json.read_text(encoding="utf-8"))
        elif book_id in catalog_by_id:
            record = {
                **build_metadata(catalog_by_id[book_id], summaries.get(book_id, "")),
                "table_of_contents": [],
                "introduction": None,
                "passages": [],
                "conclusion": None,
                "index_terms": [],
            }
            missing_json_fallback += 1
        else:
            record = {
                "gutenberg_id": book_id,
                "table_of_contents": [],
                "introduction": None,
                "passages": [],
                "conclusion": None,
                "index_terms": [],
            }
            missing_json_fallback += 1

        record["full_text"] = full_text
        (ENRICHED_BOOKS / f"{book_id}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        written += 1

    print(
        f"Done. Wrote {written} enriched records to {ENRICHED_BOOKS} "
        f"(built fallback metadata for {missing_json_fallback})."
    )


if __name__ == "__main__":
    main()