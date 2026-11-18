"""Book records for the API: loads data/books/*.json once and turns raw records into what a result
card shows. Nothing here knows how the books were embedded; see api/README.md."""
import json
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BOOKS_DIR = ROOT_DIR / "data" / "books"
LCC_PATH = LCC_PATH = ROOT_DIR / "embedding" / "lcc_hierarchy.json"
# Saved by ingestion/download_covers.py; served by the API at /covers/{id}.jpg.
COVERS_DIR = ROOT_DIR / "data" / "raw" / "covers"

COVER_URL = "https://www.gutenberg.org/cache/epub/{id}/pg{id}.cover.medium.jpg"
SNIPPET_CHARS = 320

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
    # Commas inside parentheses aren't name parts: 'McCormick & Co. (Baltimore, Md.)' stays as it is.
    parts = [p.strip() for p in re.split(r",(?![^()]*\))", catalog_name) if p.strip()]
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

def _parse_locc(code: str) -> tuple[str, float | None]:
    """Splits 'F350.5' -> ('F', 350.5), 'AC1' -> ('AC', 1.0), 'BX' -> ('BX', None)."""
    m = re.match(r"^([A-Z]{1,3})\s*(\d+(?:\.\d+)?)?", code.strip().upper())
    if not m:
        return "", None
    letters, num = m.group(1), m.group(2)
    return letters, float(num) if num is not None else None

def _match_child(children: dict, letters: str, num: float | None) -> tuple[str | None, dict | None]:
    """Finds the matching child range or exact number at the current tree depth."""
    if not children or num is None:
        return None, None

    best_key, best_node = None, None
    best_span = float("inf")

    for key, node in children.items():
        m = re.match(rf"^{re.escape(letters)}(\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?))?$", key)
        if not m:
            continue
        start = float(m.group(1))
        end = float(m.group(2)) if m.group(2) is not None else start
        if start <= num <= end:
            span = end - start
            if span < best_span:
                best_span = span
                best_key, best_node = key, node

    return best_key, best_node

def _clean_label(raw: str) -> str:
    label = re.split(r",?\s+see\s+", raw)[0]
    return label.rstrip(" ,.")

def lcc_trail(code: str, outline: dict) -> list[dict]:
    """Walks as deep as possible from Main Class -> Subclass -> Nested Ranges/Numbers.
    Examples:
    - 'BX'  -> [{'code': 'B', 'label': 'Philosophy. Psychology. Religion'}, {'code': 'BX', 'label': 'Christian Denominations'}]
    - 'B105' -> [{'code': 'B', 'label': 'Philosophy. Psychology. Religion'}, {'code': 'B*', 'label': 'Philosophy (General)'}, ...]
    - 'AC'  -> [{'code': 'A', 'label': 'General Works'}, {'code': 'AC', 'label': 'Collections. Series. Collected works'}]
    - 'AC1' -> [{'code': 'A', 'label': 'General Works'}, {'code': 'AC1-999', ...}, {'code': 'AC1-195', ...}, {'code': 'AC1-8', ...}]"""
    if not code:
        return []
    letters, num = _parse_locc(code)
    if not letters:
        return [{"code": code, "label": code}]

    trail = []

    def add(c: str, raw_label: str | None):
        if not c or not raw_label:
            return
        label = _clean_label(raw_label)
        # If two consecutive levels share the exact same title (e.g. Subclass AC and AC1-999),
        # upgrade the code to the more specific one rather than showing duplicate text.
        if trail and trail[-1]["label"].lower() == label.lower():
            trail[-1] = {"code": c, "label": label}
            return
        trail.append({"code": c, "label": label})

    # 1. Main class (e.g. "B" -> "Philosophy. Psychology. Religion")
    main_letter = letters[0]
    main_node = outline.get(main_letter)
    if not main_node:
        return [{"code": code, "label": code}]
    add(main_letter, main_node.get("title") or main_letter)

    # 2. Subclass (only emit when it's a 2+ letter subclass like "BX";
    #    single-letter subclasses like "S" duplicate the main class letter)
    sub_node = (main_node.get("children") or {}).get(letters)
    if not sub_node:
        if len(letters) > 1:
            add(letters, letters)
        return trail

    if len(letters) > 1:
        if sub_node.get("title"):
            add(letters, sub_node["title"])
        elif num is None:
            add(letters, letters)

    # 3. Walk down nested ranges/numbers (AC1-999 -> AC1-195 -> AC1-8)
    curr = sub_node
    while curr and curr.get("children"):
        child_key, child_node = _match_child(curr["children"], letters, num)
        if not child_key or not child_node:
            break
        add(child_key, child_node.get("title"))
        curr = child_node

    return trail

def lcc_filter_label(lcc_filter: str, outline: dict) -> str | None:
    """Resolves the display label for the active `lcc` filter banner in the UI."""
    if not lcc_filter:
        return None
    flt = lcc_filter.strip().upper()
    if flt.endswith("*") and len(flt) == 2:
        sub = ((outline.get(flt[0]) or {}).get("children") or {}).get(flt[0])
        return _clean_label(sub["title"]) if sub and sub.get("title") else flt[0]
    main_node = outline.get(flt[0])
    if len(flt) == 1 and main_node:
        return _clean_label(main_node.get("title") or flt)
    probe = flt.split("-", 1)[0]
    trail = lcc_trail(probe, outline)
    for item in reversed(trail):
        if item["code"] == flt:
            return item["label"]
    return trail[-1]["label"] if trail else flt

def locc_matches(book_codes: list[str], lcc_filter: str) -> bool:
    """Checks if any of a book's LoC codes fall under a class ('B'), single-letter subclass ('B*'),
    multi-letter subclass ('BX'), exact number ('AC200'), or range ('AC1-8') filter."""
    if not lcc_filter:
        return True
    flt = lcc_filter.strip().upper()

    # Exact single-letter subclass filter ("B*" -> only subclass B, not BC/BX)
    if flt.endswith("*") and len(flt) == 2:
        target = flt[0]
        for raw in book_codes or []:
            b_letters, _ = _parse_locc(raw)
            if b_letters == target:
                return True
        return False

    # Range filter ("AC1-8")
    range_m = re.match(r"^([A-Z]{1,3})(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)$", flt)
    if range_m:
        f_letters, start, end = range_m.group(1), float(range_m.group(2)), float(range_m.group(3))
        for raw in book_codes or []:
            b_letters, b_num = _parse_locc(raw)
            if b_letters == f_letters and b_num is not None and start <= b_num <= end:
                return True
        return False

    # Exact number filter ("AC200")
    num_m = re.match(r"^([A-Z]{1,3})(\d+(?:\.\d+)?)$", flt)
    if num_m:
        f_letters, f_num = num_m.group(1), float(num_m.group(2))
        for raw in book_codes or []:
            b_letters, b_num = _parse_locc(raw)
            if b_letters == f_letters and b_num == f_num:
                return True
        return False

    # Main class ("B" -> B, BC, BX...) or multi-letter subclass ("BX" -> BX only)
    for raw in book_codes or []:
        b_letters, _ = _parse_locc(raw)
        if len(flt) == 1:
            if b_letters.startswith(flt):
                return True
        else:
            if b_letters == flt:
                return True
    return False


def card(record: dict, outline: dict, covers_dir: Path = COVERS_DIR) -> dict:
    """The fields a result row shows. Every result in /api/search carries one of these."""
    gid = int(record["gutenberg_id"])
    issued = record.get("issued") or ""
    trails = []
    seen_trails = set()
    for c in record.get("locc") or []:
        trail = lcc_trail(c, outline)
        if not trail:
            continue
        sig = tuple(p["code"] for p in trail)
        if sig not in seen_trails:
            seen_trails.add(sig)
            trails.append(trail)
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
        "locc": trails,
        "classes": [
            {"code": l, "label": _clean_label(outline[l]["title"]) if outline.get(l, {}).get("title") else l}
            for l in dict.fromkeys(c[0] for c in record.get("locc") or [] if c)
        ],
        "url": record.get("url") or f"https://www.gutenberg.org/ebooks/{gid}",
        # Our own copy when it was downloaded, so covers don't depend on gutenberg.org being up.
        "cover_url": f"/covers/{gid}.jpg" if (covers_dir / f"{gid}.jpg").exists() else COVER_URL.format(id=gid),
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


def sentences(text: str) -> list[str]:
    """Splits a snippet into sentences so "Why this book" can point at the closest one."""
    out = []
    for piece in re.split(r"(?:(?<=[.!?;])|(?<=[.!?;][)\]\"']))\s+(?=[\"'(\[A-Z0-9])", " ".join(text.split())):
        # Abbreviations and initials ("Dr.", "St.", "A. M.") split too early; glue those back together.
        if out and re.search(r"\b[A-Z][a-z]{0,2}\.$", out[-1]):
            out[-1] += " " + piece
        elif piece:
            out.append(piece)
    return out
