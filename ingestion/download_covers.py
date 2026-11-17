"""Save a cover image for every book in data/books/, so the app can serve covers itself.

Covers come from gutenberg.pglaf.org, Gutenberg's official mirror, and go to
data/raw/covers/{id}.jpg (gitignored, about 18 MB for 1,000 books). Books already saved are
skipped, so rerunning only fetches what's missing. A book without a cover is skipped and the app
shows a letter placeholder for it.

Usage: python ingestion/download_covers.py [--limit N]
"""

import argparse
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path

import certifi
from tqdm import tqdm

COVER_URL = "https://gutenberg.pglaf.org/cache/epub/{id}/pg{id}.cover.medium.jpg"

DATA = Path(__file__).resolve().parent.parent / "data"
BOOKS = DATA / "books"
COVERS = DATA / "raw" / "covers"
# Some Python builds (e.g. python.org's on macOS) ship without root certificates; certifi's bundle works everywhere.
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def fetch_cover(gutenberg_id: int, tries: int = 3) -> bytes | None:
    """The medium cover image for one book, or None if Gutenberg has none. Retries timeouts and
    connection errors, since the mirror is sometimes slow; raises after the last try."""
    req = urllib.request.Request(COVER_URL.format(id=gutenberg_id), headers={"User-Agent": "gutenberg-ingest"})
    for attempt in range(1, tries + 1):
        try:
            with urllib.request.urlopen(req, timeout=60, context=SSL_CONTEXT) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == tries:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == tries:
                raise
        finally:
            time.sleep(0.3)  # be polite to the mirror
        time.sleep(5 * attempt)  # back off before retrying


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--limit", type=int, help="only the first N books (default: all)")
    args = parser.parse_args()

    COVERS.mkdir(parents=True, exist_ok=True)
    ids = sorted(int(p.stem) for p in BOOKS.glob("*.json"))[: args.limit]
    missing = [i for i in ids if not (COVERS / f"{i}.jpg").exists()]
    no_cover, failed = 0, []
    for gid in tqdm(missing, desc="covers"):
        try:
            data = fetch_cover(gid)
        except (urllib.error.URLError, TimeoutError) as e:
            failed.append(gid)
            tqdm.write(f"{gid}: gave up ({e}); rerun the script to retry")
            continue
        if data is None:
            no_cover += 1
            continue
        (COVERS / f"{gid}.jpg").write_bytes(data)
    print(f"{len(ids) - len(missing)} already saved, {len(missing) - no_cover - len(failed)} downloaded, "
          f"{no_cover} without a cover, {len(failed)} failed")


if __name__ == "__main__":
    main()
