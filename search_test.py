from pathlib import Path
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

ROOT_DIR = Path(__file__).resolve().parent
INDEX_DIR = ROOT_DIR / "gutenberg_faiss_test"

def search_books(vectorstore, query: str, top_k: int = 5):
    # Fetch extra candidates in case multiple passages from the same book score high
    candidates = vectorstore.similarity_search_with_score(query, k=top_k * 5)

    seen_book_ids = set()
    results = []
    for doc, l2_distance in candidates:
        book_id = doc.metadata["gutenberg_id"]
        if book_id in seen_book_ids:
            continue  # skip duplicate hits from the exact same book
        seen_book_ids.add(book_id)

        # Convert L2 squared distance to cosine similarity (0.0 to 1.0, higher = better)
        similarity = 1.0 - (float(l2_distance) / 2.0)
        results.append((doc, similarity))
        if len(results) == top_k:
            break

    return results

def main():
    embeddings = HuggingFaceEmbeddings(
        model_name="BAAI/bge-base-en-v1.5",  # must match the model used in test_script.py
        encode_kwargs={"normalize_embeddings": True},
    )

    vectorstore = FAISS.load_local(
        str(INDEX_DIR),
        embeddings,
        allow_dangerous_deserialization=True,
    )

    query = "peaceful diplomacy without military conflict"
    results = search_books(vectorstore, query, top_k=5)

    for doc, score in results:
        matched_via = doc.metadata.get("doc_type", "summary")
        print(
            f"[{score:.3f}] {doc.metadata['gutenberg_id']} | {doc.metadata['title']}"
            f" (matched via: {matched_via})"
        )
        # Show the matched excerpt or summary snippet
        snippet = doc.page_content.split("Excerpt: ")[-1][:220]
        print(f"    -> {snippet}...\n")


if __name__ == "__main__":
    main()