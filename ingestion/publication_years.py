"""Exploratory: guesses each book's original publication year from several sources.

Gutenberg's `issued` is the date a book was added to Gutenberg, not when it was first published, and
the catalog has no original date. This collects candidate years from four places and keeps the ones
that agree. It writes data/raw/publication_years.json and does not change data/books/.

Sources:
- summary:    Gutenberg's own summary, when it says "published in 1916". Most summaries only give an era
              ("written in the early 20th century"), which is used as a range check instead
- title_page: years on the book's title page, preferring imprint lines ("London: ... 1916", "Copyright, 1912")
- openlibrary: Open Library search by title and author surname; its first_publish_year is often a
               modern reprint, so the earliest edition year in the author's lifetime is used instead
- wikidata:   works linked to the Gutenberg ID (P2034), or found by title with a matching author

Every candidate must fit the author's dates (from age 15 to 10 years after death), the Gutenberg
release, and the summary's era with a 10-year margin (the summaries are machine-written). A year is
"high" confidence when two sources agree within a year. Open Library alone is not trusted when there
are no author dates or era to check it against, because its years are often modern reprints.

Run: python ingestion/publication_years.py [--limit N]   (~25 min for 1,000 books; title pages are
cached in data/raw/title_pages/ so reruns are fast)
"""
import argparse
import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import certifi

from download_full_texts import download_text
from ingest import strip_boilerplate

ROOT = Path(__file__).resolve().parent.parent
BOOKS = ROOT / "data" / "books"
RAW = ROOT / "data" / "raw"
TITLE_PAGES = RAW / "title_pages"
OUT = RAW / "publication_years.json"
UA = {"User-Agent": "cds-capstone-research/0.1 (semantic search over Project Gutenberg)"}
CTX = ssl.create_default_context(cafile=certifi.where())
YEAR = re.compile(r"\b(1[4-9]\d\d|20[0-2]\d)\b")
IMPRINT = re.compile(r"london|new york|boston|philadelphia|chicago|edinburgh|oxford|cambridge|paris|"
                     r"press|publish|printed|copyright|edition|sons|company|co\.", re.I)
ERA = re.compile(r"\b(early|mid|late)[- ](1[5-9]|20)(?:st|nd|rd|th) century", re.I)
SUMMARY = re.compile(r"\b(?:published|written|printed|issued|composed|appeared|released)\b[^.]{0,40}?\b(1[5-9]\d\d)\b", re.I)


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, context=CTX, timeout=30) as resp:
        return json.load(resp)


def lifespan(record: dict) -> tuple[int, int, bool]:
    """Earliest and latest plausible year, from the first author's dates, the Gutenberg release and the
    summary's era. The flag says whether either check was available."""
    released = int((record.get("issued") or "2100")[:4])
    authors = [c for c in record.get("contributors") or [] if c.get("role") == "Author"]
    dates = re.findall(r"(\d{3,4})\??(?: BCE)?-(\d{3,4})?", authors[0]["name"]) if authors else []
    lo, hi = 1450, released
    if dates:
        born, died = dates[-1]
        lo = max(lo, int(born) + 15)
        if died:
            hi = min(hi, int(died) + 10)
    era = ERA.search(record.get("description") or "")
    if era:
        start = (int(era.group(2)) - 1) * 100 + {"early": 0, "mid": 33, "late": 66}[era.group(1).lower()]
        lo, hi = max(lo, start - 10), min(hi, start + 34 + 10)
    return lo, hi, bool(dates or era)


def surname(record: dict) -> str:
    authors = [c for c in record.get("contributors") or [] if c.get("role") == "Author"]
    return authors[0]["name"].split(",")[0].strip() if authors else ""


def from_summary(record: dict) -> list[int]:
    return [int(y) for y in SUMMARY.findall(record.get("description") or "")]


def title_page(gid: int) -> str:
    """The first ~6,000 characters of the book, cached so reruns don't download again."""
    path = TITLE_PAGES / f"{gid}.txt"
    if not path.exists():
        text = download_text(gid)
        path.write_text((strip_boilerplate(text) or text)[:6000], encoding="utf-8")
        time.sleep(0.5)  # politeness delay for the mirror
    return path.read_text(encoding="utf-8")


def from_title_page(gid: int) -> list[int]:
    """Years on imprint lines first; other years only when no imprint line has one."""
    lines = title_page(gid).splitlines()
    imprint = [int(y) for line in lines if IMPRINT.search(line) for y in YEAR.findall(line)]
    return imprint or [int(y) for line in lines for y in YEAR.findall(line)]


def from_openlibrary(record: dict, lo: int, hi: int) -> list[int]:
    """The earliest edition year that fits the author's lifetime, for the best title + author match."""
    q = {"title": record.get("title") or "", "author": surname(record), "limit": 3,
         "fields": "title,first_publish_year,publish_year"}
    docs = get_json("https://openlibrary.org/search.json?" + urllib.parse.urlencode(q)).get("docs") or []
    for doc in docs:
        years = sorted(y for y in doc.get("publish_year") or [] if lo <= y <= hi)
        if years:
            return [years[0]]
    return []


def from_wikidata(record: dict) -> list[int]:
    """A Wikidata work with this Gutenberg ID, or with this title and an author with this surname."""
    gid, name = record["gutenberg_id"], surname(record).replace('"', "")
    title = (record.get("title") or "").replace('"', "").replace("\\", "")[:200]
    query = f"""SELECT ?date WHERE {{
      {{ ?w wdt:P2034 "{gid}" }} UNION {{ ?w rdfs:label "{title}"@en ; wdt:P50 ?a . ?a rdfs:label ?an .
         FILTER(LANG(?an) = "en" && CONTAINS(?an, "{name}")) }}
      {{ ?w wdt:P577 ?date }} UNION {{ ?w wdt:P629/wdt:P577 ?date }} }} LIMIT 5"""
    url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(query)
    rows = get_json(url)["results"]["bindings"]
    return [int(r["date"]["value"][:4]) for r in rows if r["date"]["value"][:4].isdigit()]


def safe(fn, *args) -> list[int] | str:
    try:
        return fn(*args)
    except Exception as e:  # one failing source shouldn't drop the other three
        return f"error: {type(e).__name__}"


def combine(cands: dict[str, list[int] | str], lo: int, hi: int, checked: bool) -> dict:
    """Keeps years within the lifespan, then picks the year most sources agree on (within one year)."""
    ok = {src: sorted({y for y in ys if lo <= y <= hi}) for src, ys in cands.items() if isinstance(ys, list)}
    ok = {src: ys for src, ys in ok.items() if ys}
    votes = Counter()
    for src, ys in ok.items():
        for y in {y for y in ys}:
            votes[y] += 1
    if not votes:
        return {"year": None, "confidence": None, "sources": []}
    # Two sources within a year of each other agree.
    support = {y: len({s for s, ys in ok.items() if any(abs(y - z) <= 1 for z in ys)}) for y in votes}
    best = max(support.values())
    if best >= 2:
        year = min(y for y, n in support.items() if n == best)  # the earliest agreed year
        srcs = [s for s, ys in ok.items() if any(abs(year - z) <= 1 for z in ys)]
        return {"year": year, "confidence": "high", "sources": srcs}
    # One source only: trust the summary, then the title page imprint, then Open Library, then Wikidata.
    # On a title page the imprint year usually comes last; earlier years are often dates the book cites
    # (the latest year matched Open Library for 411 of 523 books, the earliest for 349).
    for src in ("summary", "title_page", "wikidata", "openlibrary"):
        if src in ok and (src != "openlibrary" or checked):
            year = max(ok[src]) if src == "title_page" else min(ok[src])
            return {"year": year, "confidence": "low", "sources": [src]}
    return {"year": None, "confidence": None, "sources": []}


def one_book(record: dict) -> dict:
    lo, hi, checked = lifespan(record)
    gid = int(record["gutenberg_id"])
    cands = {"summary": from_summary(record), "title_page": safe(from_title_page, gid),
             "openlibrary": safe(from_openlibrary, record, lo, hi), "wikidata": safe(from_wikidata, record)}
    return {"gutenberg_id": gid, "title": record.get("title"), "range": [lo, hi], "candidates": cands,
            **combine(cands, lo, hi, checked)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    TITLE_PAGES.mkdir(parents=True, exist_ok=True)
    records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(BOOKS.glob("*.json"))][:args.limit]
    with ThreadPoolExecutor(4) as pool:  # four at a time: polite to each service, done in ~25 min
        rows = list(pool.map(one_book, records))
    OUT.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    conf = Counter(r["confidence"] for r in rows)
    print(f"{len(rows)} books: high {conf['high']}, low {conf['low']}, none {conf[None]} -> {OUT}")
    for src in ("summary", "title_page", "openlibrary", "wikidata"):
        hits = sum(1 for r in rows if isinstance(r["candidates"][src], list) and r["candidates"][src])
        errs = sum(1 for r in rows if isinstance(r["candidates"][src], str))
        print(f"  {src:<12} has a year for {hits}, errors {errs}")


if __name__ == "__main__":
    main()
