"""Choose which Gutenberg books we use, fetch their texts, and save full texts for inspecting the data.

The subset is English nonfiction in a fixed random order (books are ordered by a hash of their ID),
so a larger --limit keeps the same books and adds more. This script saves the first N of them to
data/raw/full-texts/{id}.txt, skipping books already saved. ingest.py imports the subset and text
fetching from here, and reads texts from that folder when present instead of downloading them again.

Usage: python ingestion/download_full_texts.py [--limit 25]
"""

import argparse
import csv
import hashlib
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from tqdm import tqdm

CATALOG_URL = "https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv"
# Gutenberg asks bulk downloaders to use mirrors rather than gutenberg.org.
MIRROR = "https://mirrors.xmission.com/gutenberg"

DATA = Path(__file__).resolve().parent.parent / "data"
RAW = DATA / "raw"
FULL_TEXTS = RAW / "full-texts"

LATER_VOLUME = re.compile(r"\bvol(?:ume|\.)?\s+([0-9]+|[ivxlc]+)\b", re.I)


def download(url):
    req = urllib.request.Request(url, headers={"User-Agent": "gutenberg-ingest"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    time.sleep(0.5)  # be polite to the server
    return data


def fetch(url, path):
    """Download `url` to `path` unless it's already cached. Returns the path."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(download(url))
    return path


def wanted(row):
    """English nonfiction books, excluding periodicals and volumes after the first."""
    if row["Type"] != "Text" or row["Language"] != "en":
        return False
    # LoC class P is language & literature (novels, poetry, drama).
    if any(c.strip().startswith("P") for c in row["LoCC"].split(";")):
        return False
    if re.search(r"\bfiction\b", row["Subjects"], re.I) or re.search(r"\bPeriodicals\b", row["Subjects"]):
        return False
    volume = LATER_VOLUME.search(row["Title"])
    if volume and volume.group(1).lower() not in ("1", "01", "i"):
        return False
    return True


def load_subset():
    """Catalog rows for the books we want, in a fixed random order."""
    catalog = fetch(CATALOG_URL, RAW / "pg_catalog.csv")
    with open(catalog, encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if wanted(r)]
    # A hash of the ID gives a random order that stays the same as the catalog grows.
    rows.sort(key=lambda r: hashlib.sha256(r["Text#"].encode()).hexdigest())
    return rows


def download_text(book_id):
    """Read a book's plain text from data/raw/full-texts/ if it's there, otherwise fetch it from the mirror
    without saving it. Returns None if the mirror doesn't have it."""
    saved = FULL_TEXTS / f"{book_id}.txt"
    if saved.exists():
        return saved.read_text(encoding="utf-8")
    digits = str(book_id)
    folder = "/".join(digits[:-1]) or "0"  # mirror layout: 2701 -> 2/7/0/2701/
    # {id}-0.txt is UTF-8; older books only have {id}.txt, which is plain ASCII.
    for filename in (f"{digits}-0.txt", f"{digits}.txt"):
        try:
            return download(f"{MIRROR}/{folder}/{digits}/{filename}").decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=25, help="number of books to save (default: 25)")
    args = parser.parse_args()

    FULL_TEXTS.mkdir(parents=True, exist_ok=True)
    saved = 0
    progress = tqdm(total=args.limit, unit="book")
    for row in load_subset():
        if saved >= args.limit:
            break
        book_id = int(row["Text#"])
        path = FULL_TEXTS / f"{book_id}.txt"
        if not path.exists():
            text = download_text(book_id)
            if text is None:
                tqdm.write(f"[Skipped] {book_id}: no plain text on mirror")
                continue
            path.write_text(text, encoding="utf-8")
        saved += 1
        progress.update()
    progress.close()

    print(f"Done. {saved} full texts in {FULL_TEXTS}")


if __name__ == "__main__":
    main()
