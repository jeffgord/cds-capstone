"""Standalone sandbox script to clean saved full texts and report length stats.

Reuses boilerplate stripping and inline cleanup from ingest.py without modifying
existing ingestion files or touching data/books/.

Usage:
    python ingestion/clean_full_texts_sandbox.py
    python ingestion/clean_full_texts_sandbox.py --tag exp1
"""

import argparse
import statistics
import sys
from pathlib import Path

from tqdm import tqdm

REPO_ROOT = Path(__file__).resolve().parent.parent
INGEST_DIR = Path(__file__).resolve().parent
if str(INGEST_DIR) not in sys.path:
    sys.path.insert(0, str(INGEST_DIR))

from download_full_texts import DATA, FULL_TEXTS  # noqa: E402
from ingest import clean, strip_boilerplate  # noqa: E402


def percentile(sorted_vals, q):
    if not sorted_vals:
        return 0.0
    idx = (len(sorted_vals) - 1) * q
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def resolve_out_dir(tag: str | None) -> Path:
    base = DATA / "cleaned"
    if tag:
        return base / tag / "full-texts"
    return base / "full-texts"


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--tag",
        type=str,
        default=None,
        help="optional experiment subfolder under data/cleaned/<tag>/full-texts",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="compute and print stats without writing cleaned files",
    )
    args = parser.parse_args()

    out_dir = resolve_out_dir(args.tag)
    files = sorted(FULL_TEXTS.glob("*.txt"), key=lambda p: int(p.stem))
    if not files:
        print(f"No .txt files found in {FULL_TEXTS}", flush=True)
        return

    if not args.no_write:
        out_dir.mkdir(parents=True, exist_ok=True)

    raw_chars, raw_words = [], []
    clean_chars, clean_words = [], []
    skipped = 0
    short_books = []

    for path in tqdm(files, unit="book"):
        raw_text = path.read_text(encoding="utf-8", errors="replace")
        body = strip_boilerplate(raw_text)
        if not body:
            tqdm.write(f"[Skipped] {path.stem}: no START/END markers")
            skipped += 1
            continue

        cleaned_text = clean(body).strip()
        raw_chars.append(len(raw_text))
        raw_words.append(len(raw_text.split()))
        clean_chars.append(len(cleaned_text))
        clean_words.append(len(cleaned_text.split()))

        if clean_words[-1] < 1000:
            short_books.append((path.stem, clean_words[-1], clean_chars[-1]))

        if not args.no_write:
            (out_dir / path.name).write_text(cleaned_text + "\n", encoding="utf-8")

    sc_sorted = sorted(clean_chars)
    sw_sorted = sorted(clean_words)

    print(
        f"\nProcessed {len(clean_words)} books (skipped {skipped} missing START/END markers).",
        flush=True,
    )
    if not args.no_write:
        print(f"Saved cleaned texts to: {out_dir}")
    print(
        f"Words: {sum(raw_words):,} -> {sum(clean_words):,} "
        f"({sum(clean_words) / max(sum(raw_words), 1) * 100:.1f}% kept)"
    )
    print(
        f"Chars: {sum(raw_chars):,} -> {sum(clean_chars):,} "
        f"({sum(clean_chars) / max(sum(raw_chars), 1) * 100:.1f}% kept)"
    )
    print(
        f"Cleaned words — mean: {statistics.mean(clean_words):,.1f}, "
        f"median: {statistics.median(clean_words):,.1f}, "
        f"P10/P90: {percentile(sw_sorted, 0.10):,.0f} / {percentile(sw_sorted, 0.90):,.0f}, "
        f"min/max: {min(clean_words):,} / {max(clean_words):,}"
    )
    print(
        f"Cleaned chars — mean: {statistics.mean(clean_chars):,.1f}, "
        f"median: {statistics.median(clean_chars):,.1f}, "
        f"P10/P90: {percentile(sc_sorted, 0.10):,.0f} / {percentile(sc_sorted, 0.90):,.0f}, "
        f"min/max: {min(clean_chars):,} / {max(clean_chars):,}"
    )

    if short_books:
        print(f"\nBooks with < 1,000 cleaned words ({len(short_books)}):")
        for book_id, w, c in sorted(short_books, key=lambda x: x[1])[:15]:
            print(f"  {book_id}.txt: {w:,} words ({c:,} chars)")


if __name__ == "__main__":
    main()