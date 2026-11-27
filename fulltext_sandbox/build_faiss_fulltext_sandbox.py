import argparse
import os
from pathlib import Path
import sys
import time

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.faiss import DistanceStrategy
from langchain_huggingface import HuggingFaceEmbeddings
import torch

from embedding.create_embed_document_fulltext import MODEL_NAME, build_documents

DATA_DIR = ROOT_DIR / "data" / "enriched_books"


def default_scratch_index_dir() -> Path:
    scratch_base = Path(os.environ.get("SCRATCH") or f"/scratch/{os.environ.get('USER', 'user')}")
    return scratch_base / "gutenberg_faiss_fulltext"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build full-text FAISS index on GPU in $SCRATCH.")
    parser.add_argument("--limit", type=int, default=None, help="number of books to index (default: all)")
    parser.add_argument("--batch-size", type=int, default=128, help="embedding batch size (default: 128)")
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=default_scratch_index_dir(),
        help="output directory for FAISS index (default: $SCRATCH/gutenberg_faiss_fulltext)",
    )
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")
    if device == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    t0 = time.perf_counter()
    docs = build_documents(
        DATA_DIR,
        limit=args.limit,
        include_full_text=True,
        chunk_tokens=350,
        chunk_overlap=50,
    )
    print(f"Built {len(docs):,} documents in {time.perf_counter() - t0:.1f}s")

    embeddings = HuggingFaceEmbeddings(
        model_name=MODEL_NAME,
        model_kwargs={"device": device},
        encode_kwargs={"normalize_embeddings": True, "batch_size": args.batch_size},
    )

    t1 = time.perf_counter()
    print("Embedding documents and building FAISS index...")
    vectorstore = FAISS.from_documents(
        docs,
        embeddings,
        distance_strategy=DistanceStrategy.COSINE,
    )
    embed_elapsed = time.perf_counter() - t1

    args.index_dir.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(args.index_dir))
    print(f"Embedded {len(docs):,} docs in {embed_elapsed:.1f}s ({len(docs) / max(embed_elapsed, 1e-6):.0f} docs/s)")
    print(f"Saved FAISS index to {args.index_dir}")


if __name__ == "__main__":
    main()