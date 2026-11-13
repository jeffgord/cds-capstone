"""Book records for the API: loads data/books/*.json once and turns raw records into what a result
card shows. Nothing here knows how the books were embedded; see api/README.md."""
import json
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BOOKS_DIR = ROOT_DIR / "data" / "books"
LCC_PATH = ROOT_DIR / "embedding" / "lcc_outline.json"

COVER_URL = "https://www.gutenberg.org/cache/epub/{id}/pg{id}.cover.medium.jpg"
SNIPPET_CHARS = 320

# Small on purpose: it only decides which query words count as "shared words" in the UI.
STOPWORDS = set("""
a about above after again against all also am an and any are as at be because been before being
below between both but by can could did do does doing down during each few for from further had has
have having he her here hers him his how i if in into is it its itself just me more most my no nor
not of off on once only or other our out over own same she should so some such than that the their
them then there these they this those through to too under until up very was we were what when where
which while who whom why will with would you your book books about want looking find something like
""".split())

# Subclasses missing or cut off in embedding/lcc_outline.json, which was scraped from the first page
# of each LoC outline PDF. Values from the LoC Classification Outline.
LCC_SUPPLEMENT = {
    "DJ": "Netherlands (Holland)", "DJK": "Eastern Europe (General)",
    "DK": "Russia. Soviet Union. Former Soviet Republics. Poland", "DL": "Northern Europe. Scandinavia",
    "DP": "Spain. Portugal", "DQ": "Switzerland", "DR": "Balkan Peninsula", "DS": "Asia", "DT": "Africa",
    "DU": "Oceania (South Seas)", "DX": "Romanies",
    "HN": "Social history and conditions. Social problems. Social reform",
    "KD": "Law of the United Kingdom and Ireland", "KF": "Law of the United States",
    "Z": "Books (General). Writing. Paleography. Book industries and trade. Libraries. Bibliography",
}

DATE_PART = re.compile(r"\d")  # "1826-1914", "427? BCE-347? BCE", "active 1700"
HONORIFICS = {"sir", "dame", "lady", "lord", "mrs.", "mr.", "rev.", "dr.", "saint"}
PEERAGE = {"baron", "baroness", "earl", "count", "countess", "viscount", "viscountess", "marquis",
           "marquess", "duke", "duchess", "graf", "prince", "princess"}
NAME_SUFFIXES = {"jr.", "sr.", "ii", "iii", "iv"}


def load_books(books_dir: Path = BOOKS_DIR) -> dict[int, dict]:
    books = {}
    for path in sorted(books_dir.glob("*.json")):
        with path.open(encoding="utf-8") as f:
            record = json.load(f)
        books[int(record["gutenberg_id"])] = record
    return books


def load_lcc(path: Path = LCC_PATH) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def display_name(catalog_name: str) -> str:
    """'Sylvain, Adrien, 1826-1914' -> 'Adrien Sylvain (1826-1914)'.
    'Yonge, Charlotte M. (Charlotte Mary), 1823-1901' -> 'Charlotte M. Yonge (1823-1901)'.
    'Davy, Humphry, Sir, 1778-1829' -> 'Sir Humphry Davy (1778-1829)'.
    'Birkenhead, Frederick Edwin Smith, Earl of, 1872-1930' -> 'Frederick Edwin Smith, Earl of Birkenhead (1872-1930)'.
    'Thomas, Aquinas, Saint, 1225?-1274' -> 'Saint Thomas Aquinas (1225?-1274)'. No comma: unchanged.
    Cases come from the 1,206 contributor names in the 1,000-book dataset (see tests/test_api.py)."""
    catalog_name = re.sub(r"[​-‏]", "", catalog_name)  # stray direction marks ('Wycliffe, John‏')
    parts = [p.strip() for p in catalog_name.split(",") if p.strip()]
    if len(parts) < 2:
        return catalog_name.strip()
    surname = parts[0]
    dates = [p for p in parts[1:] if DATE_PART.search(p)]
    names = [re.sub(r"\s*\([^)]*\)", "", p) for p in parts[1:] if not DATE_PART.search(p)]
    given, extras = (names[0], names[1:]) if names else ("", [])
    honorifics = [x for x in extras if x.lower() in HONORIFICS]
    peerage = [x for x in extras if x.split()[0].lower() in PEERAGE]
    suffixes = [x for x in extras if x.lower() in NAME_SUFFIXES]
    postnominals = [x for x in extras if x not in honorifics + peerage + suffixes]  # "F.S.A.", "cook"

    if any(h.lower() == "saint" for h in honorifics):  # surname is the saint's own name here
        name = " ".join(["Saint", surname, given])
    elif peerage:
        title = peerage[0]
        if re.search(r"\b(of|de|von)$", title):  # 'Earl of' + Birkenhead
            name = f"{given}, {title} {surname}"
        elif title.endswith("'"):  # "baron d'" + Holbach
            name = f"{given}, {title}{surname}"
        elif surname.split()[0] in given:  # British peer: 'James Bryce, Viscount Bryce'
            name = f"{given}, {title} {surname}"
        else:  # 'Cuvier, Georges, baron' reads best as plain 'Georges Cuvier'
            name = f"{given} {surname}"
    else:
        joined = f"{given}{surname}" if given.endswith("-") else f"{given} {surname}"  # 'Cecil Harcourt-Smith'
        name = " ".join([*honorifics, joined.strip(), *suffixes])
    if postnominals:
        name += ", " + ", ".join(postnominals)
    if dates:
        d = dates[-1]
        d = f"died {d[1:]}" if d.startswith("-") else f"born {d[:-1]}" if d.endswith("-") else d
        name += f" ({d})"
    return name


def lcc_label(code: str, outline: dict) -> str:
    """Subclass label when the outline has one ('BV' -> 'Practical theology'), else the class title."""
    if not code:
        return ""
    letters = re.match(r"[A-Z]+", code)  # Gutenberg sometimes has full numbers ("D501")
    entry = outline.get(code[0])
    if not entry or not letters:
        return code
    label = LCC_SUPPLEMENT.get(letters.group()) or entry.get("subclasses", {}).get(letters.group())
    if not label:
        title = (entry.get("title") or code).rstrip(" ,.")
        if title.isupper():  # class titles are upper case in the outline ("PHILOSOPHY. PSYCHOLOGY. RELIGION")
            small = {"and", "of", "the", "in", "for"}
            words = title.lower().replace(".", ",").split()
            title = " ".join(w if w in small and i else w.capitalize() for i, w in enumerate(words))
        label = title
    label = re.split(r",?\s+see\s+", label)[0]  # drop outline cross-references ("..., see JZ and KZ")
    return label.rstrip(" ,.")


def card(record: dict, outline: dict) -> dict:
    """The fields a result row shows. Every result in /api/search carries one of these."""
    gid = int(record["gutenberg_id"])
    issued = record.get("issued") or ""
    return {
        "title": record.get("title") or "Untitled",
        "subtitle": record.get("subtitle") or None,
        "authors": [
            {"name": c["name"], "display": display_name(c["name"]), "role": c.get("role") or "Author"}
            for c in sorted(record.get("contributors") or [], key=lambda c: c.get("order", 0))
        ],
        # `issued` is the Gutenberg release date, not the original publication date.
        "added_year": int(issued[:4]) if issued[:4].isdigit() else None,
        # Gutenberg's summaries are auto-generated; the UI labels them that way.
        "description": (record.get("description") or "").strip() or None,
        "subjects": record.get("subjects") or [],
        "topic_subjects": record.get("topic_subjects") or [],
        "locc": [{"code": c, "label": lcc_label(c, outline)} for c in record.get("locc") or [] if c],
        "url": record.get("url") or f"https://www.gutenberg.org/ebooks/{gid}",
        "cover_url": COVER_URL.format(id=gid),
    }


def detail(record: dict, outline: dict) -> dict:
    """Card plus the extracted text, for the detail panel."""
    return {
        "gutenberg_id": int(record["gutenberg_id"]),
        **card(record, outline),
        "table_of_contents": record.get("table_of_contents") or [],
        "introduction": record.get("introduction") or None,
        "passages": record.get("passages") or [],
        "has_text": bool(record.get("table_of_contents") or record.get("introduction") or record.get("passages")),
    }


def _shorten(text: str, limit: int = SNIPPET_CHARS) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",.;:") + "..."


def snippet(record: dict, doc_type: str | None, passage_index: int | None, text: str | None) -> str | None:
    """What the "Why this book" box quotes. Prefers the book's own text over the embedded string,
    because index builders prefix chunks with headers ("Title: ... | Subjects: ... | Excerpt: ")."""
    passages = record.get("passages") or []
    description = (record.get("description") or "").strip()
    if doc_type == "summary" and description:
        return _shorten(description)
    if passage_index is not None and 0 <= passage_index < len(passages):
        return _shorten(passages[passage_index])
    if text:
        if "Excerpt: " in text:
            return _shorten(text.split("Excerpt: ", 1)[1])
        if not text.lstrip().startswith("Title:"):
            return _shorten(text)
    if description:
        return _shorten(description)
    toc = record.get("table_of_contents") or []
    return _shorten("; ".join(toc)) if toc else None


def query_terms(query: str) -> list[str]:
    words = re.findall(r"[a-z0-9']+", query.lower())
    return list(dict.fromkeys(w.strip("'") for w in words if len(w) > 2 and w not in STOPWORDS))


def stem(term: str) -> str:
    # Crude on purpose ("immigrants" matches "immigrant"); this is word overlap, not the model. The UI
    # highlights words that start with the stem, so "studi" catches study and studies.
    if term.endswith("ies") and len(term) > 4:
        return term[:-3] + "i"
    if re.search(r"(ss|us|is)$", term):  # glass, census, analysis
        return term
    if re.search(r"(x|z|ch|sh|ss)es$", term):  # boxes, churches
        return term[:-2]
    if term.endswith("s") and len(term) > 3:
        return term[:-1]
    return term


def fields_matched(record: dict, query: str) -> list[dict]:
    """Which card fields literally contain a query word. Shown as "Your words also appear in", never as
    the model's reason for the match."""
    fields = {
        "title": " ".join(filter(None, [record.get("title"), record.get("subtitle")])),
        "author": " ".join(c["name"] for c in record.get("contributors") or []),
        "subjects": " ".join((record.get("subjects") or []) + (record.get("topic_subjects") or [])),
        "summary": record.get("description") or "",
    }
    terms = query_terms(query)
    out = []
    for field, value in fields.items():
        value = value.lower()
        hits = [t for t in terms if re.search(r"\b" + re.escape(stem(t)), value)]
        if hits:
            out.append({"field": field, "terms": hits})
    return out
