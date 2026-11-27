import json
from pathlib import Path
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from transformers import AutoTokenizer

from embedding.preprocess import format_book

MODEL_NAME = "BAAI/bge-base-en-v1.5"


def build_documents(
    data_dir: Path,
    limit: int | None = None,
    include_full_text: bool = True,
    chunk_tokens: int = 350,
    chunk_overlap: int = 50,
) -> list[Document]:
    book_files = sorted(data_dir.rglob("*.json"))
    if limit is not None:
        book_files = book_files[:limit]

    splitter = None
    if include_full_text:
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        # model_max_length is 512; leave ~100 tokens headroom for header + special tokens
        safe_chunk_size = min(chunk_tokens, 400)
        splitter = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
            tokenizer,
            chunk_size=safe_chunk_size,
            chunk_overlap=chunk_overlap,
        )

    docs: list[Document] = []
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
                metadata={**base_meta, "doc_type": "summary", "passage_index": -1, "chunk_index": -1},
            )
        )

        title = book.get("title", "")
        subjects = "; ".join(book.get("subjects") or [])
        header = f"Title: {title}" + (f" | Subjects: {subjects}" if subjects else "")

        # 2. Up to 6 passage documents
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
                        "chunk_index": -1,
                    },
                )
            )

        # 3. Full-text chunks (when present in enriched JSON)
        full_text = (book.get("full_text") or "").strip()
        if include_full_text and splitter is not None and full_text:
            chunks = splitter.split_text(full_text)
            total_chunks = len(chunks)
            for c_idx, chunk in enumerate(chunks):
                chunk_text = chunk.strip()
                if not chunk_text:
                    continue
                docs.append(
                    Document(
                        page_content=f"{header} | Chunk {c_idx + 1}/{total_chunks}: {chunk_text}",
                        metadata={
                            **base_meta,
                            "doc_type": "full_text_chunk",
                            "passage_index": -1,
                            "chunk_index": c_idx,
                            "total_chunks": total_chunks,
                        },
                    )
                )

    return docs