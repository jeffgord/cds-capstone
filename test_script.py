from pathlib import Path
from embedding.create_embed_document import build_documents
from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.faiss import DistanceStrategy
from langchain_huggingface import HuggingFaceEmbeddings

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data" / "books"
INDEX_DIR = ROOT_DIR / "gutenberg_faiss_test"


def main():
    # 1. Load all books and create summary + passage Documents
    docs = build_documents(DATA_DIR, limit=None)
    print(f"Total documents built (summaries + passages): {len(docs)}")

    # 2. Initialize the embedding model (512-token limit, 768 dims)
    embeddings = HuggingFaceEmbeddings(
        model_name="BAAI/bge-base-en-v1.5",
        encode_kwargs={"normalize_embeddings": True},
    )

    # 3. Embed all documents and build the FAISS index
    print("Embedding documents and building FAISS index...")
    vectorstore = FAISS.from_documents(
        docs,
        embeddings,
        distance_strategy=DistanceStrategy.COSINE,
    )

    # 4. Save the index to disk so search_test.py can load it instantly
    vectorstore.save_local(str(INDEX_DIR))
    print(f"Saved FAISS index to {INDEX_DIR}")


if __name__ == "__main__":
    main()