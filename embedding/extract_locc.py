import io
import json
import re
import time
from pathlib import Path

import pdfplumber
import requests

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

BASE_URL = (
    "https://loc.gov/aba/cataloging/classification/lcco/lcco_{}.pdf"
)

LOOKUP_FILE = Path("lcc_lookup.json")
HIERARCHY_FILE = Path("lcc_hierarchy.json")

LETTERS = [
    "A", "B", "C", "D", "E", "F", "G", "H", "J",
    "K", "L", "M", "N", "P", "Q", "R", "S", "T",
    "U", "V", "Z"
]

# E and F are contained in one combined PDF
PDF_GROUPS = {
    letter: letter.lower() for letter in LETTERS if letter not in ("E", "F")
}

PDF_GROUPS["E"] = "ef"
PDF_GROUPS["F"] = "ef"

HEADERS = {
    "User-Agent": "LCC-Classification-Extractor/1.0"
}

# ---------------------------------------------------------
# PDF Downloading
# ---------------------------------------------------------

def download_pdf(letter, retries=3):
    """Download a Library of Congress classification PDF."""
    pdf_name = PDF_GROUPS[letter]
    url = BASE_URL.format(pdf_name)

    for attempt in range(1, retries + 1):
        try:
            print(f"Downloading {url}")
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=(15, 120)
            )
            response.raise_for_status()
            if not response.content.startswith(b"%PDF"):
                raise ValueError("Downloaded file is not a valid PDF.")
            return response.content
        except (requests.RequestException, ValueError) as error:
            print(
                f"Download failed for {letter} "
                f"(attempt {attempt}/{retries}): {error}"
            )
            if attempt < retries:
                time.sleep(2 * attempt)

    return None

# ---------------------------------------------------------
# Text Normalization
# ---------------------------------------------------------

def normalize_code(code):
    """Normalize a classification code."""
    return re.sub(r"\s+", "", code.strip()).upper()

def clean_title(title):
    """Clean extracted classification titles."""
    return re.sub(r"\s+", " ", title).strip()

def format_class_title(raw):
    """Convert 'PHILOSOPHY. PSYCHOLOGY. RELIGION' -> 'Philosophy. Psychology. Religion'."""
    small = {"and", "of", "the", "in", "for"}
    words = clean_title(raw).lower().split()
    return " ".join(w if w in small and i else w.capitalize() for i, w in enumerate(words))

# ---------------------------------------------------------
# Classification Extraction
# ---------------------------------------------------------

def extract_entries_from_pdf(pdf_bytes, allowed_letters):
    """Extract main classes, subclasses, and numeric ranges/numbers from a LoC PDF."""
    entries = {}
    pending_subclass = None

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()
            if not text:
                continue

            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue

                # 0. Main class heading:
                # Handles "CLASS B - PHILOSOPHY..." AND combined "CLASS E - F - HISTORY OF THE AMERICAS"
                match = re.match(
                    r"^CLASS\s+([A-Z])(?:\s*[-–—]\s*([A-Z]))?\s*[-–—]\s*(.+)$",
                    line,
                    re.IGNORECASE,
                )
                if match:
                    c1 = normalize_code(match.group(1))
                    c2 = normalize_code(match.group(2)) if match.group(2) else None
                    title = format_class_title(match.group(3))
                    for cls_code in filter(None, (c1, c2)):
                        if cls_code in allowed_letters:
                            entries[f"CLASS:{cls_code}"] = {
                                "code": cls_code,
                                "title": title,
                                "type": "class",
                                "page": page_number,
                            }
                    pending_subclass = None
                    continue

                # 1. Subclass marker and title on the same line: "Subclass B Philosophy (General)"
                match = re.match(
                    r"^Subclass\s+([A-Z]{1,3})\s+(.+)$",
                    line,
                    re.IGNORECASE
                )
                if match:
                    code = normalize_code(match.group(1))
                    title = clean_title(match.group(2))
                    if code[0] in allowed_letters:
                        entries[code] = {
                            "title": title,
                            "type": "subclass",
                            "page": page_number
                        }
                    pending_subclass = None
                    continue

                # 2. Standalone subclass marker: "Subclass KD"
                match = re.match(
                    r"^Subclass\s+([A-Z]{1,3})$",
                    line,
                    re.IGNORECASE
                )
                if match:
                    code = normalize_code(match.group(1))
                    pending_subclass = code if code[0] in allowed_letters else None
                    continue

                # 3. Subclass title on the following line: "KD Law of the United Kingdom"
                if pending_subclass:
                    match = re.match(
                        rf"^{re.escape(pending_subclass)}\s+(.+)$",
                        line,
                        re.IGNORECASE
                    )
                    if match:
                        title = clean_title(match.group(1))
                        if not re.match(r"^\d", title):
                            entries[pending_subclass] = {
                                "title": title,
                                "type": "subclass",
                                "page": page_number
                            }
                            pending_subclass = None
                            continue
                    pending_subclass = None

                # 4. Numbered classification entries and ranges: "AC1-999 Collections..."
                match = re.match(
                    r"^([A-Z]{1,3})\s*"
                    r"(\d+(?:\.\d+)?)"
                    r"(?:\s*-\s*(\d+(?:\.\d+)?))?"
                    r"\s+(.+)$",
                    line,
                    re.IGNORECASE
                )
                if match:
                    prefix = match.group(1).upper()
                    if prefix[0] not in allowed_letters:
                        continue
                    start = match.group(2)
                    end = match.group(3)
                    title = clean_title(match.group(4))
                    code = f"{prefix}{start}" + (f"-{end}" if end else "")
                    entries[code] = {
                        "title": title,
                        "type": "range" if end else "number",
                        "page": page_number
                    }

    return entries

# ---------------------------------------------------------
# Lookup & Hierarchy Construction
# ---------------------------------------------------------

def build_lookup(progress):
    """Combine all extracted schedules into one lookup."""
    lookup = {}
    for letter in LETTERS:
        lookup.update(progress.get(letter, {}))
    return lookup

def _parse_num_range(code):
    """Parses 'AC1-999' -> ('AC', 1.0, 999.0), 'AC200' -> ('AC', 200.0, 200.0)."""
    m = re.match(r"^([A-Z]{1,3})(\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?))?$", code)
    if not m:
        return None
    prefix = m.group(1)
    start = float(m.group(2))
    end = float(m.group(3)) if m.group(3) is not None else start
    return prefix, start, end

def build_hierarchy(lookup):
    """Builds Main Class -> Subclass -> Broad Range -> Narrow Range/Number."""
    hierarchy = {}

    # 1. Create root main class nodes ("A", "B", ...)
    for key, data in lookup.items():
        if data.get("type") == "class":
            c = data["code"]
            hierarchy[c] = {
                "title": data["title"],
                "type": "class",
                "page": data.get("page"),
                "children": {},
            }

    # 2. Attach subclasses ("AC", "B", "BC", "BX", ...) under their main class
    subclasses = {}
    for code, data in sorted(lookup.items()):
        if data.get("type") != "subclass":
            continue
        main_letter = code[0]
        hierarchy.setdefault(main_letter, {
            "title": main_letter, "type": "class", "page": 1, "children": {}
        })
        node = {
            "title": data["title"],
            "type": "subclass",
            "page": data.get("page"),
            "children": {},
        }
        hierarchy[main_letter]["children"][code] = node
        subclasses[code] = node

    # 3. Group numeric entries by subclass prefix and nest ranges by containment
    by_prefix = {}
    for code, data in lookup.items():
        if data.get("type") not in ("range", "number"):
            continue
        parsed = _parse_num_range(code)
        if not parsed:
            continue
        prefix, start, end = parsed
        by_prefix.setdefault(prefix, []).append((start, end, code, data))

    for prefix, items in by_prefix.items():
        sub_node = subclasses.get(prefix)
        if not sub_node:
            main_letter = prefix[0]
            hierarchy.setdefault(main_letter, {
                "title": main_letter, "type": "class", "page": 1, "children": {}
            })
            # Title is None so lcc_trail won't emit a redundant "E (E)" pill
            sub_node = {"title": None, "type": "subclass", "page": None, "children": {}}
            hierarchy[main_letter]["children"][prefix] = sub_node

        # Sort broadest ranges first (smallest start, largest span)
        items.sort(key=lambda x: (x[0], -(x[1] - x[0]), x[2]))
        placed = []

        for start, end, code, data in items:
            node = {
                "title": data["title"],
                "type": data["type"],
                "page": data.get("page"),
                "children": {},
            }
            enclosing = [
                (p_end - p_start, p_node)
                for p_start, p_end, p_node in placed
                if p_start <= start and end <= p_end and (p_start, p_end) != (start, end)
            ]
            if enclosing:
                _, parent_node = min(enclosing, key=lambda x: x[0])
                parent_node["children"][code] = node
            else:
                sub_node["children"][code] = node

            if data["type"] == "range":
                placed.append((start, end, node))

    return hierarchy

# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():
    extracted = {}

    print("=" * 60)
    print("LIBRARY OF CONGRESS CLASSIFICATION EXTRACTOR")
    print("=" * 60)

    for letter in LETTERS:
        print(f"\nProcessing schedule {letter}...")
        pdf_bytes = download_pdf(letter)
        if not pdf_bytes:
            print(f"Could not download PDF for {letter}.")
            continue

        entries = extract_entries_from_pdf(pdf_bytes, {letter})
        extracted[letter] = entries
        print(f"Extracted {len(entries)} entries for schedule {letter}.")
        time.sleep(1)

    lookup = build_lookup(extracted)
    with open(LOOKUP_FILE, "w", encoding="utf-8") as file:
        json.dump(lookup, file, indent=2, ensure_ascii=False)

    hierarchy = build_hierarchy(lookup)
    with open(HIERARCHY_FILE, "w", encoding="utf-8") as file:
        json.dump(hierarchy, file, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print("EXTRACTION COMPLETE")
    print("=" * 60)
    print(f"Total extracted entries: {len(lookup)}")
    print(f"Saved lookup to: {LOOKUP_FILE}")
    print(f"Saved hierarchy to: {HIERARCHY_FILE}")

if __name__ == "__main__":
    main()