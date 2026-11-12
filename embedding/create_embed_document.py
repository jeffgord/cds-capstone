import json
from pathlib import Path
from embedding.preprocess import format_book
from langchain_core.documents import Document

def build_documents(data_dir: Path, limit: int | None = None) -> list[Document]:
    book_files = sorted(data_dir.rglob("*.json"))
    if limit is not None:
        book_files = book_files[:limit]

    docs = []
    for file_path in book_files:
        with file_path.open("r", encoding="utf-8") as f:
            book = json.load(f)

            base_meta = {
                "gutenberg_id": book.get("gutenberg_id"),
                "title": book.get("title", ""),
                "language": book.get("language", ""),
                "locc": book.get("locc", []),
                "url": book.get("url", ""),
            }

            # 1. Main catalog + summary document
            docs.append(
                Document(
                    page_content=format_book(book),
                    metadata={**base_meta, "doc_type": "summary", "passage_index": -1},
                )
            )

            # 2. Up to 6 passage documents (with title + subjects header for context)
            title = book.get("title", "")
            subjects = "; ".join(book.get("subjects") or [])
            header = f"Title: {title}" + (f" | Subjects: {subjects}" if subjects else "")

            for idx, passage in enumerate(book.get("passages") or []):
                if not passage or not passage.strip():
                    continue
                docs.append(
                    Document(
                        page_content=f"{header} | Excerpt: {passage.strip()}",
                        metadata={
                            **base_meta,
                            "doc_type": "passage",
                            "passage_index": idx,
                        },
                    )
                )

    return docs