import json
from pathlib import Path

EMBEDDING_DIR = Path(__file__).resolve().parent
LOCC_PATH = EMBEDDING_DIR / "lcc_outline.json"

with LOCC_PATH.open("r", encoding="utf-8") as f:
    LOCC_MAP = json.load(f)

def _extract_locc_label(entry) -> str:
    if isinstance(entry, str):
        label = entry
    if isinstance(entry, dict):
        # Adjust key order if your lcc_outline.json uses a different field name
        label = (entry.get("title") or entry.get("name") or entry.get("label") or entry.get("description") or "")
    return label.rstrip(", ").title()

# preprocess gutenberg's json into clean text strings
def format_book(record: dict) -> str:
    authors = ", ".join(c["name"] for c in record.get("contributors", []))
    all_subjects = list(
        dict.fromkeys(
            record.get("subjects", []) + record.get("topic_subjects", [])
        )
    )
    subjects_str = "; ".join(all_subjects)
    locc_labels = []
    for code in record.get("locc", []):
        if not code:
            continue
        raw_entry = LOCC_MAP.get(code) or LOCC_MAP.get(code[0])
        label = _extract_locc_label(raw_entry)
        if label:
            locc_labels.append(label)

    locc_str = "; ".join(dict.fromkeys(locc_labels))
    description = record.get("description") or ""

    return (
        f"Title: {record.get('title', '')} | "
        f"Author: {authors} | "
        f"Subjects: {subjects_str} | "
        f"Classification: {locc_str} | "
        f"Summary: {description}"
        )